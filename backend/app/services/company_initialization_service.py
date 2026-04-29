from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.config import settings
from app.data_sources.factory import announcement_provider, company_profile_provider, financial_provider, news_provider
from app.models.models import BusinessLine, Company, InvestmentHypothesis, JobRun
from app.services.announcement_fetch_service import AnnouncementFetchService
from app.services.financial_fetch_service import FinancialFetchService
from app.services.job_run_service import JobRunService
from app.services.news_fetch_service import NewsFetchService


COMMON_BUSINESS_KEYWORDS = ['产品', '业务', '项目', '订单', '客户', '产能', '销售', '服务', '平台', '系统', '新能源', '智能', '材料', '设备', '软件', '芯片', '医药', '消费']
RISK_KEYWORDS = ['减持', '亏损', '诉讼', '处罚', '问询函', '资产减值', '担保', '应收账款', '存货', '现金流']


class CompanyInitializationService:
    def __init__(self, db: Session):
        self.db = db

    def initialize(self, code: str, market: str | None = None):
        run = JobRunService(self.db).start('initialize_company')
        result = self._empty_result(code, market)
        try:
            self._run_stage(result, 'basic_info', lambda: self._load_basic_info(result, code, market))
            self._run_stage(result, 'announcements', lambda: self._load_announcements(result))
            self._run_stage(result, 'news', lambda: self._load_news(result))
            self._run_stage(result, 'financials', lambda: self._load_financials(result))
            self._run_stage(result, 'drafts', lambda: self._build_drafts(result))
            JobRunService(self.db).success(run, result)
            return {'task_id': run.id, 'status': 'success'}
        except Exception as exc:
            result['errors'].append({'stage': 'fatal', 'error': str(exc)})
            JobRunService(self.db).failed(run, str(exc), result)
            return {'task_id': run.id, 'status': 'failed'}

    def get_status(self, task_id: int):
        run = self.db.get(JobRun, task_id)
        if not run or run.job_name != 'initialize_company':
            return None
        return {'task_id': run.id, 'status': run.status, 'started_at': run.started_at, 'finished_at': run.finished_at, 'result': run.result_summary or {}, 'error_message': run.error_message}

    def confirm(self, task_id: int, payload: dict):
        status = self.get_status(task_id)
        if not status:
            return None
        result = status['result']
        basic = {**(result.get('basic_info') or {}), **(payload.get('basic_info') or {})}
        code = basic.get('code')
        company = self.db.query(Company).filter(Company.code == code).first()
        if not company:
            company = Company(code=code, name=basic.get('name') or code, market=basic.get('market') or 'A', status='watching')
            self.db.add(company)
        company.name = basic.get('name') or company.name or code
        company.market = basic.get('market') or company.market or 'A'
        company.industry = basic.get('industry') or company.industry
        company.main_business = basic.get('main_business') or company.main_business
        if payload.get('save_research', True):
            company.thesis = payload.get('draft_thesis', result.get('draft_thesis') or company.thesis)
            disproof = payload.get('draft_disproof_conditions', result.get('draft_disproof_conditions') or [])
            company.disproof_conditions = '\n'.join(disproof) if isinstance(disproof, list) else disproof
        self.db.commit()
        self.db.refresh(company)

        if payload.get('save_research', True):
            line_ids = []
            for line in payload.get('draft_business_lines', result.get('draft_business_lines') or []):
                if not line.get('name'):
                    continue
                exists = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id, BusinessLine.name == line['name']).first()
                if exists:
                    line_ids.append(exists.id)
                    continue
                business_line = BusinessLine(company_id=company.id, name=line['name'], role=line.get('role'), description=line.get('description'), keywords=line.get('keywords') or [], key_metrics=', '.join(line.get('key_metrics') or []), confidence=line.get('confidence') or 'low', generated_by=line.get('source') or 'rule')
                self.db.add(business_line)
                self.db.flush()
                line_ids.append(business_line.id)
            if not self.db.query(InvestmentHypothesis).filter(InvestmentHypothesis.company_id == company.id).first():
                disproof = payload.get('draft_disproof_conditions', result.get('draft_disproof_conditions') or [])
                self.db.add(InvestmentHypothesis(
                    company_id=company.id,
                    title=(payload.get('draft_thesis') or result.get('draft_thesis') or f'{company.name} 核心经营逻辑待验证')[:120],
                    description=payload.get('draft_thesis') or result.get('draft_thesis'),
                    related_business_line_ids=line_ids,
                    falsification_conditions=disproof if isinstance(disproof, list) else [disproof],
                    status='unverified',
                    review_status='pending',
                    generated_by='rule',
                ))
            self.db.commit()

        ingest = {}
        try:
            ingest['announcements'] = AnnouncementFetchService(self.db).fetch(company.id, record_job=False)
        except Exception as exc:
            ingest['announcements_error'] = str(exc)
        try:
            ingest['news'] = NewsFetchService(self.db).fetch(company.id, record_job=False)
        except Exception as exc:
            ingest['news_error'] = str(exc)
        try:
            ingest['financials'] = FinancialFetchService(self.db).fetch(company.id, record_job=False)
        except Exception as exc:
            ingest['financials_error'] = str(exc)
        return {'company_id': company.id, 'ingest': ingest}

    def _empty_result(self, code: str, market: str | None):
        return {'basic_info': {'code': code, 'name': '', 'market': market or '', 'industry': '', 'main_business': ''}, 'draft_thesis': '', 'draft_disproof_conditions': [], 'draft_business_lines': [], 'draft_risks': [], 'recent_announcements': [], 'recent_news': [], 'financial_summary': {}, 'stages': [], 'errors': []}

    def _run_stage(self, result: dict, stage: str, fn):
        result['stages'].append({'stage': stage, 'status': 'running'})
        try:
            fn()
            result['stages'][-1]['status'] = 'success'
        except Exception as exc:
            result['stages'][-1]['status'] = 'failed'
            result['errors'].append({'stage': stage, 'error': str(exc)})

    def _load_basic_info(self, result: dict, code: str, market: str | None):
        dto = company_profile_provider().fetch_company_profile(code, market)
        result['basic_info'].update({'code': code, 'name': dto.name or code, 'market': dto.market or market or 'A', 'industry': dto.industry or '', 'main_business': dto.main_business or ''})

    def _load_announcements(self, result: dict):
        code = result['basic_info']['code']
        start = date.today() - timedelta(days=settings.fetch_lookback_days_announcement)
        items = announcement_provider().fetch_announcements(code, start, date.today())
        if items and (not result['basic_info'].get('name') or result['basic_info'].get('name') == code):
            stock_name = items[0].stock_name
            if stock_name:
                result['basic_info']['name'] = stock_name
        result['recent_announcements'] = [{'title': i.title, 'stock_name': i.stock_name, 'publish_time': i.publish_time.isoformat(), 'source': i.source, 'url': i.url} for i in items[:10]]

    def _load_news(self, result: dict):
        basic = result['basic_info']
        company = SimpleNamespace(code=basic['code'], name=basic.get('name') or basic['code'])
        keywords = [company.name, company.code]
        items = news_provider().fetch_company_news(company, keywords, settings.fetch_max_news_per_company)
        result['recent_news'] = [{'title': i.title, 'publish_time': i.publish_time.isoformat(), 'source': i.source, 'url': i.url, 'summary': i.summary} for i in items[:10]]

    def _load_financials(self, result: dict):
        items = financial_provider().fetch_financial_snapshots(result['basic_info']['code'])
        if not items:
            result['financial_summary'] = {'message': '数据暂缺'}
            return
        latest = items[0]
        result['financial_summary'] = {'report_period': latest.report_period, 'revenue': latest.revenue, 'net_profit': latest.net_profit, 'operating_cash_flow': latest.operating_cash_flow, 'gross_margin': latest.gross_margin, 'roe': latest.roe}

    def _build_drafts(self, result: dict):
        basic = result['basic_info']
        texts = [basic.get('main_business') or '', basic.get('industry') or '']
        texts.extend(item['title'] for item in result.get('recent_announcements', []))
        texts.extend(item['title'] for item in result.get('recent_news', []))
        hit_keywords = [k for k in COMMON_BUSINESS_KEYWORDS if any(k in text for text in texts)]
        risk_hits = [k for k in RISK_KEYWORDS if any(k in text for text in texts)]
        industry = basic.get('industry') or '主营业务'
        line_name = industry if industry and industry != 'A' else (hit_keywords[0] if hit_keywords else '核心业务')
        result['draft_business_lines'] = [{
            'name': line_name,
            'role': 'core',
            'description': basic.get('main_business') or f"根据公告、新闻和行业信息生成的 {line_name} 草案。",
            'keywords': list(dict.fromkeys([line_name, *hit_keywords, basic.get('name'), basic.get('code')]))[:12],
            'key_metrics': ['营业收入', '归母净利润', '经营现金流', '毛利率'],
            'confidence': 'medium' if hit_keywords or basic.get('main_business') else 'low',
            'source': 'rule',
        }]
        result['draft_thesis'] = f"初步关注 {basic.get('name') or basic.get('code')} 的{line_name}经营变化、订单/产品进展、盈利质量和现金流表现。该草案由规则生成，需人工复核。"
        risks = risk_hits or ['业绩下滑', '经营现金流转弱', '应收账款或存货异常增加', '重大诉讼/处罚/减持']
        result['draft_risks'] = [{'title': risk, 'source': 'rule', 'confidence': 'medium' if risk in risk_hits else 'low'} for risk in risks]
        result['draft_disproof_conditions'] = [f"{risk} 持续出现或影响主营业务质量" for risk in risks[:6]]
