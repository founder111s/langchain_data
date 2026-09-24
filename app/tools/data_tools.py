"""数据集信息工具：list_datasets / select_dataset。"""
import json
import logging

from langchain_core.tools import tool

from app.data.loader import load_all_meta, load_dataset
from app.tools.convert import df_to_jsonable

logger = logging.getLogger(__name__)


@tool
def list_datasets() -> str:
    """列出所有可用数据集及其字段说明，返回 JSON 字符串。"""
    return json.dumps(load_all_meta(), ensure_ascii=False, indent=2)


@tool
def select_dataset(name: str) -> str:
    """加载指定数据集（name 来自 list_datasets），返回行数列数与字段预览。"""
    try:
        df = load_dataset(name)
        return json.dumps(
            {
                "name": name,
                "shape": list(df.shape),
                "preview": df_to_jsonable(df.head(5)),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("select_dataset 失败")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
