CATEGORIES = {
    '定期报告': ['年度报告', '半年度报告', '季度报告', '一季报', '三季报'],
    '业绩类': ['业绩预告', '业绩快报'],
    '订单类': ['重大合同', '中标', '项目', '订单'],
    '风险类': ['减持', '资产减值', '诉讼', '仲裁', '担保', '关联交易', '高管离职'],
    '调研类': ['投资者关系活动记录', '调研', '业绩说明会'],
    '分红类': ['利润分配', '权益分派'],
}


def classify_text(text: str) -> str:
    for category, keywords in CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            return category
    return '其他'
