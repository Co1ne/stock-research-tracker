import logging
import math
import socket
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from app.core.config import settings
from app.data_sources.base import AnnouncementDTO, CompanyProfileDTO, FinancialSnapshotDTO, NewsDTO, QuoteDTO

logger = logging.getLogger(__name__)


@contextmanager
def request_timeout(seconds: int):
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(seconds)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous)


def _load_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError('akshare is not installed; install backend requirements first') from exc
    return ak


def _first(row: dict[str, Any], names: list[str]):
    for name in names:
        if name in row and row[name] not in (None, ''):
            return row[name]
    return None


def _to_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if value is None:
        return datetime.utcnow()
    text = str(value).replace('/', '-').split('.')[0]
    if len(text) == 8 and text.count(':') == 2:
        today = date.today()
        text = f'{today.isoformat()} {text}'
    parsed = datetime.fromisoformat(text)
    return parsed


def _to_float(value):
    if value in (None, '', '-', '--'):
        return None
    try:
        return float(str(value).replace(',', '').replace('%', ''))
    except (TypeError, ValueError):
        return None


def _clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _clean_value(value) for key, value in row.items()}


def _infer_market(stock_code: str) -> str:
    if stock_code.startswith(('60', '68', '900')):
        return 'SH'
    if stock_code.startswith(('00', '30', '20')):
        return 'SZ'
    if stock_code.startswith(('8', '4')):
        return 'BJ'
        return 'A'


def _with_market_suffix(stock_code: str) -> str:
    market = _infer_market(stock_code)
    suffix = {'SH': 'SH', 'SZ': 'SZ', 'BJ': 'BJ'}.get(market, '')
    return f'{stock_code}.{suffix}' if suffix else stock_code


class AkshareProvider:
    source_name = 'akshare'

    def fetch_company_profile(self, stock_code: str, market: str | None = None) -> CompanyProfileDTO:
        ak = _load_akshare()
        logger.info('fetching akshare company profile stock=%s', stock_code)
        row_map = {}
        with request_timeout(settings.fetch_timeout_seconds):
            try:
                df = ak.stock_individual_info_em(symbol=stock_code)
                rows = df.to_dict('records') if hasattr(df, 'to_dict') else []
                for row in rows:
                    key = _first(row, ['item', '项目', '指标'])
                    value = _first(row, ['value', '值', '内容'])
                    if key:
                        row_map[str(key)] = value
            except Exception as exc:
                logger.warning('akshare company profile failed stock=%s error=%s', stock_code, exc)
        name = row_map.get('股票简称') or row_map.get('简称') or row_map.get('股票名称')
        industry = row_map.get('行业') or row_map.get('所属行业')
        return CompanyProfileDTO(
            stock_code=stock_code,
            name=str(name) if name else None,
            market=market or _infer_market(stock_code),
            industry=str(industry) if industry else None,
            main_business=str(row_map.get('主营业务')) if row_map.get('主营业务') else None,
            source='akshare',
            extra=row_map,
        )

    def fetch_announcements(self, stock_code: str, start_date: date | None, end_date: date | None) -> list[AnnouncementDTO]:
        ak = _load_akshare()
        start = (start_date or date.today()).strftime('%Y%m%d')
        end = (end_date or date.today()).strftime('%Y%m%d')
        logger.info('fetching akshare announcements stock=%s start=%s end=%s', stock_code, start, end)
        with request_timeout(settings.fetch_timeout_seconds):
            try:
                df = ak.stock_zh_a_disclosure_report_cninfo(symbol=stock_code, start_date=start, end_date=end)
            except TypeError:
                df = ak.stock_zh_a_disclosure_report_cninfo(symbol=stock_code)
        rows = df.to_dict('records') if hasattr(df, 'to_dict') else []
        items = []
        for row in rows:
            title = _first(row, ['公告标题', '标题', 'announcementTitle', 'title'])
            if not title:
                continue
            items.append(AnnouncementDTO(
                stock_code=stock_code,
                stock_name=_first(row, ['证券简称', '简称', 'stock_name', 'secName']),
                title=str(title),
                publish_time=_to_datetime(_first(row, ['公告时间', '发布日期', 'publish_time', 'announcementTime'])),
                source='akshare:cninfo',
                url=_first(row, ['公告链接', 'url', 'adjunctUrl', '公告地址']),
                extra=row,
            ))
        return items

    def fetch_company_news(self, company, keywords: list[str], limit: int = 20) -> list[NewsDTO]:
        ak = _load_akshare()
        logger.info('fetching akshare news company=%s code=%s', company.name, company.code)
        try:
            with request_timeout(settings.fetch_timeout_seconds):
                try:
                    df = ak.stock_news_em(symbol=company.code)
                except TypeError:
                    df = ak.stock_news_em(symbol=company.name)
        except Exception as exc:
            logger.warning('akshare stock_news_em failed company=%s code=%s error=%s', company.name, company.code, exc)
            try:
                df = self._fetch_cls_news_fallback(ak, company, keywords)
            except Exception as fallback_exc:
                logger.warning('akshare cls news fallback failed company=%s code=%s error=%s', company.name, company.code, fallback_exc)
                rows = []
                df = None
        rows = rows if 'rows' in locals() else (df.to_dict('records') if hasattr(df, 'to_dict') else [])
        items = []
        for row in rows[:limit]:
            title = _first(row, ['新闻标题', '标题', 'title'])
            if not title:
                continue
            cleaned = _clean_row(row)
            items.append(NewsDTO(
                title=str(title),
                source=str(_first(row, ['文章来源', '来源', 'source']) or 'akshare:em'),
                publish_time=_to_datetime(_first(row, ['发布时间', '时间', 'publish_time', '日期', '发布日期'])),
                url=_first(row, ['新闻链接', '链接', 'url']),
                summary=_first(row, ['新闻内容', '内容', '摘要', 'summary']),
                related_company=company.name,
                extra=cleaned,
            ))
        return items

    def _fetch_cls_news_fallback(self, ak, company, keywords: list[str]):
        with request_timeout(settings.fetch_timeout_seconds):
            df = ak.stock_info_global_cls(symbol='全部')
        rows = df.to_dict('records') if hasattr(df, 'to_dict') else []
        terms = [company.name, company.code, *keywords]
        terms = [str(term) for term in dict.fromkeys(terms) if term]
        matched = []
        for row in rows:
            text = f"{_first(row, ['标题']) or ''} {_first(row, ['内容']) or ''}"
            if any(term in text for term in terms):
                row = dict(row)
                row.setdefault('来源', '财联社')
                matched.append(row)
        return type(df)(matched) if matched else df.head(0)

    def fetch_financial_snapshots(self, stock_code: str) -> list[FinancialSnapshotDTO]:
        ak = _load_akshare()
        logger.info('fetching akshare financials stock=%s', stock_code)
        with request_timeout(settings.fetch_timeout_seconds):
            try:
                df = ak.stock_financial_analysis_indicator_em(symbol=_with_market_suffix(stock_code), indicator='按报告期')
                rows = df.to_dict('records') if hasattr(df, 'to_dict') else []
                if rows:
                    return [self._financial_from_em_row(stock_code, row) for row in rows if _first(row, ['REPORT_DATE', 'REPORT_DATE_NAME'])]
            except Exception as exc:
                logger.warning('akshare financial indicator em failed stock=%s error=%s', stock_code, exc)

            try:
                df = ak.stock_financial_analysis_indicator(symbol=stock_code, start_year=str(max(date.today().year - 3, 1900)))
            except TypeError:
                df = ak.stock_financial_analysis_indicator(symbol=stock_code)
        rows = df.to_dict('records') if hasattr(df, 'to_dict') else []
        items = []
        for row in rows:
            period = _first(row, ['日期', '报告期', 'report_period'])
            if not period:
                continue
            cleaned = _clean_row(row)
            items.append(FinancialSnapshotDTO(
                stock_code=stock_code,
                report_period=str(period),
                revenue=_to_float(_first(row, ['营业收入', '营业总收入'])),
                net_profit=_to_float(_first(row, ['归母净利润', '净利润', '扣除非经常性损益后的净利润'])),
                net_profit_deducted=_to_float(_first(row, ['扣非净利润', '扣除非经常性损益后的净利润'])),
                gross_margin=_to_float(_first(row, ['销售毛利率', '毛利率'])),
                net_margin=_to_float(_first(row, ['销售净利率', '净利率'])),
                operating_cash_flow=_to_float(_first(row, ['经营现金流量净额', '每股经营性现金流'])),
                accounts_receivable=_to_float(_first(row, ['应收账款', '应收账款周转率'])),
                inventory=_to_float(_first(row, ['存货', '存货周转率'])),
                debt_asset_ratio=_to_float(_first(row, ['资产负债率'])),
                roe=_to_float(_first(row, ['净资产收益率', 'ROE'])),
                source='akshare',
                raw_data=cleaned,
            ))
        return items

    def _financial_from_em_row(self, stock_code: str, row: dict[str, Any]) -> FinancialSnapshotDTO:
        period = _first(row, ['REPORT_DATE', 'REPORT_DATE_NAME'])
        if isinstance(period, str) and ' ' in period:
            period = period.split(' ')[0]
        return FinancialSnapshotDTO(
            stock_code=stock_code,
            report_period=str(period),
            revenue=_to_float(_first(row, ['TOTALOPERATEREVE'])),
            net_profit=_to_float(_first(row, ['PARENTNETPROFIT', 'NETPROFIT'])),
            net_profit_deducted=_to_float(_first(row, ['KCFJCXSYJLR'])),
            gross_margin=_to_float(_first(row, ['XSMLL'])),
            net_margin=_to_float(_first(row, ['XSJLL'])),
            operating_cash_flow=_to_float(_first(row, ['MGJYXJJE'])),
            debt_asset_ratio=_to_float(_first(row, ['ZCFZL'])),
            roe=_to_float(_first(row, ['ROEJQ', 'ROEKCJQ'])),
            source='akshare:em',
            raw_data=_clean_row(row),
        )

    def fetch_latest_quote(self, stock_code: str) -> QuoteDTO | None:
        ak = _load_akshare()
        with request_timeout(settings.fetch_timeout_seconds):
            df = ak.stock_zh_a_spot_em()
        rows = df.to_dict('records') if hasattr(df, 'to_dict') else []
        for row in rows:
            if str(_first(row, ['代码', 'code'])) == stock_code:
                return QuoteDTO(
                    stock_code=stock_code,
                    latest_price=_to_float(_first(row, ['最新价'])),
                    change_percent=_to_float(_first(row, ['涨跌幅'])),
                    turnover=_to_float(_first(row, ['成交额'])),
                    market_value=_to_float(_first(row, ['总市值'])),
                    source='akshare',
                )
        return None
