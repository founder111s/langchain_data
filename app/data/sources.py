"""4 个领域开源数据集定义。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str  # datetime / numeric / category / text
    desc: str


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    title: str
    description: str
    file: str
    domain: str
    fields: tuple[FieldSpec, ...]
    date_col: str | None = None
    value_cols: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "fields": [{"name": f.name, "type": f.type, "desc": f.desc} for f in self.fields],
        }


DATASETS: dict[str, DatasetSpec] = {
    "credit": DatasetSpec(
        name="credit",
        title="信用卡违约（银行风控）",
        description="UCI Default of Credit Card Clients 台湾信用卡客户数据，含信用额度、人口属性、过去6个月还款/账单记录及下月违约标签，可分析违约率与人口属性、还款行为的关系。",
        file="credit_default.csv",
        domain="银行风控",
        fields=(
            FieldSpec("ID", "text", "客户ID"),
            FieldSpec("LIMIT_BAL", "numeric", "信用额度（新台币）"),
            FieldSpec("SEX", "category", "性别（1=男，2=女）"),
            FieldSpec("EDUCATION", "category", "教育程度（1=研究生，2=大学，3=高中，4=其他）"),
            FieldSpec("MARRIAGE", "category", "婚姻状况（1=已婚，2=单身，3=其他）"),
            FieldSpec("AGE", "numeric", "年龄"),
            FieldSpec("PAY_0", "numeric", "最近一期还款状态（-1=准时，0=未消费，1-9=延迟月数）"),
            FieldSpec("PAY_2", "numeric", "前2期还款状态"),
            FieldSpec("PAY_3", "numeric", "前3期还款状态"),
            FieldSpec("PAY_4", "numeric", "前4期还款状态"),
            FieldSpec("PAY_5", "numeric", "前5期还款状态"),
            FieldSpec("PAY_6", "numeric", "前6期还款状态"),
            FieldSpec("BILL_AMT1", "numeric", "最近一期账单金额"),
            FieldSpec("BILL_AMT2", "numeric", "前2期账单金额"),
            FieldSpec("BILL_AMT3", "numeric", "前3期账单金额"),
            FieldSpec("BILL_AMT4", "numeric", "前4期账单金额"),
            FieldSpec("BILL_AMT5", "numeric", "前5期账单金额"),
            FieldSpec("BILL_AMT6", "numeric", "前6期账单金额"),
            FieldSpec("PAY_AMT1", "numeric", "最近一期还款金额"),
            FieldSpec("PAY_AMT2", "numeric", "前2期还款金额"),
            FieldSpec("PAY_AMT3", "numeric", "前3期还款金额"),
            FieldSpec("PAY_AMT4", "numeric", "前4期还款金额"),
            FieldSpec("PAY_AMT5", "numeric", "前5期还款金额"),
            FieldSpec("PAY_AMT6", "numeric", "前6期还款金额"),
            FieldSpec("DEFAULT", "category", "下月是否违约（1=是，0=否）"),
        ),
    ),
    "ecommerce": DatasetSpec(
        name="ecommerce",
        title="电商零售 Online Retail",
        description="UCI Online Retail 国际在线零售订单数据，含订单/商品/国家/日期，可分析销售额趋势、国家与商品维度。",
        file="ecommerce_retail.csv",
        domain="电商零售",
        date_col="InvoiceDate",
        value_cols=("Quantity", "UnitPrice", "Revenue"),
        fields=(
            FieldSpec("InvoiceNo", "text", "发票号"),
            FieldSpec("StockCode", "text", "商品编码"),
            FieldSpec("Description", "text", "商品描述"),
            FieldSpec("Quantity", "numeric", "数量"),
            FieldSpec("InvoiceDate", "datetime", "发票日期"),
            FieldSpec("UnitPrice", "numeric", "单价"),
            FieldSpec("CustomerID", "text", "客户ID"),
            FieldSpec("Country", "category", "国家"),
            FieldSpec("Revenue", "numeric", "销售额=数量×单价"),
        ),
    ),
    "finance": DatasetSpec(
        name="finance",
        title="金融股票行情",
        description="腾讯行情接口拉取 AAPL/MSFT/GOOG/TSLA 近一年日线（前复权，免费公开数据），可分析收盘价走势、涨跌幅与成交量。",
        file="finance_daily.csv",
        domain="金融股票",
        date_col="Date",
        value_cols=("Open", "High", "Low", "Close", "Volume"),
        fields=(
            FieldSpec("Date", "datetime", "交易日"),
            FieldSpec("Ticker", "category", "股票代码"),
            FieldSpec("Open", "numeric", "开盘价"),
            FieldSpec("High", "numeric", "最高价"),
            FieldSpec("Low", "numeric", "最低价"),
            FieldSpec("Close", "numeric", "收盘价"),
            FieldSpec("Volume", "numeric", "成交量"),
        ),
    ),
    "climate": DatasetSpec(
        name="climate",
        title="气候气象（城市日值）",
        description="Open-Meteo 历史气象档案：北京/上海/纽约/伦敦近两年逐日最高/最低温与降水，可分析季节趋势与城市对比。",
        file="climate_cities.csv",
        domain="气候气象",
        date_col="Date",
        value_cols=("tmax", "tmin", "precipitation"),
        fields=(
            FieldSpec("Date", "datetime", "日期"),
            FieldSpec("City", "category", "城市"),
            FieldSpec("tmax", "numeric", "最高气温(℃)"),
            FieldSpec("tmin", "numeric", "最低气温(℃)"),
            FieldSpec("precipitation", "numeric", "降水量(mm)"),
        ),
    ),
    "health": DatasetSpec(
        name="health",
        title="公共卫生 COVID-19",
        description="Our World in Data 公开 COVID-19 数据（部分国家，2020 至今），可分析确诊/死亡趋势与国家对比。",
        file="covid_owid.csv",
        domain="公共卫生",
        date_col="date",
        value_cols=("total_cases", "new_cases", "total_deaths", "new_deaths"),
        fields=(
            FieldSpec("date", "datetime", "日期"),
            FieldSpec("location", "category", "国家/地区"),
            FieldSpec("total_cases", "numeric", "累计确诊"),
            FieldSpec("new_cases", "numeric", "新增确诊"),
            FieldSpec("total_deaths", "numeric", "累计死亡"),
            FieldSpec("new_deaths", "numeric", "新增死亡"),
        ),
    ),
}


def dataset_names() -> list[str]:
    return list(DATASETS.keys())
