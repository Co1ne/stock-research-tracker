from sqlalchemy.orm import Session

from app.data_sources.factory import financial_provider
from app.models.models import Company, FinancialSnapshot, RiskEvent
from app.services.evidence_rule_service import EvidenceRuleService
from app.services.job_run_service import JobRunService


class FinancialFetchService:
    def __init__(self, db: Session, provider=None):
        self.db = db
        self.provider = provider or financial_provider()

    def _companies(self, company_id: int | None):
        q = self.db.query(Company).filter(Company.status != 'removed')
        if company_id:
            q = q.filter(Company.id == company_id)
        return q.order_by(Company.id.asc()).all()

    def fetch(self, company_id: int | None = None, record_job: bool = True):
        run = JobRunService(self.db).start('fetch_financials') if record_job else None
        result = {'fetched_companies': 0, 'fetched_items': 0, 'upserted': 0, 'failed_companies': [], 'warnings': []}
        try:
            for company in self._companies(company_id):
                result['fetched_companies'] += 1
                try:
                    items = self.provider.fetch_financial_snapshots(company.code)
                    result['fetched_items'] += len(items)
                    for dto in items:
                        row = self.db.query(FinancialSnapshot).filter(FinancialSnapshot.company_id == company.id, FinancialSnapshot.report_period == dto.report_period).first()
                        if not row:
                            row = FinancialSnapshot(company_id=company.id, stock_code=company.code, report_period=dto.report_period)
                            self.db.add(row)
                        row.revenue = dto.revenue
                        row.net_profit = dto.net_profit
                        row.net_profit_deducted = dto.net_profit_deducted
                        row.gross_margin = dto.gross_margin
                        row.net_margin = dto.net_margin
                        row.operating_cash_flow = dto.operating_cash_flow
                        row.accounts_receivable = dto.accounts_receivable
                        row.inventory = dto.inventory
                        row.debt_asset_ratio = dto.debt_asset_ratio
                        row.roe = dto.roe
                        row.source = dto.source
                        row.raw_data = dto.raw_data
                        result['upserted'] += 1
                        self.db.flush()
                        self._detect_financial_risk(company, row, result)
                    self.db.commit()
                except Exception as exc:
                    self.db.rollback()
                    result['failed_companies'].append({'company': company.name, 'code': company.code, 'error': str(exc)})
            if run:
                JobRunService(self.db).success(run, result)
            return result
        except Exception as exc:
            if run:
                JobRunService(self.db).failed(run, str(exc), result)
            raise

    def _detect_financial_risk(self, company: Company, row: FinancialSnapshot, result: dict):
        if row.operating_cash_flow is not None and row.net_profit is not None and row.operating_cash_flow < 0 < row.net_profit:
            title = f'{company.name} 经营现金流与净利润背离'
            risk = self._get_or_create_risk(company, row, title, 'medium', f'{row.report_period} 经营现金流为负但净利润为正')
            EvidenceRuleService(self.db).create_from_risk_event(risk)
        if row.net_profit is not None and row.net_profit < 0:
            title = f'{company.name} 归母净利润亏损'
            risk = self._get_or_create_risk(company, row, title, 'high', f'{row.report_period} 归母净利润为负')
            EvidenceRuleService(self.db).create_from_risk_event(risk)
        result['warnings'].append({'company': company.name, 'period': row.report_period, 'message': '历史数据不足时不生成同比/环比强结论'})

    def _get_or_create_risk(self, company: Company, row: FinancialSnapshot, title: str, level: str, description: str):
        risk = self.db.query(RiskEvent).filter(
            RiskEvent.company_id == company.id,
            RiskEvent.source_type == 'financial',
            RiskEvent.source_id == row.id,
            RiskEvent.title == title,
        ).first()
        if not risk:
            risk = RiskEvent(company_id=company.id, event_type='financial_rule', level=level, title=title, description=description, evidence='financial_rule', source_type='financial', source_id=row.id)
            self.db.add(risk)
            self.db.flush()
        return risk
