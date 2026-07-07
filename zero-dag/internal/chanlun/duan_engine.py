"""线段分解引擎 — czsc 包装"""
from czsc import CZSC


class DuanEngine:
    def decompose(self, bars: list) -> dict:
        if len(bars) < 5:
            return {"bi_list": [], "bi_count": 0, "last_direction": "unknown"}

        try:
            c = CZSC(bars, max_bi_num=500)
        except Exception as e:
            return {"error": str(e), "bi_count": 0}

        bi_list = []
        for bi in c.bi_list:
            bi_list.append({
                "high": float(bi.high), "low": float(bi.low),
                "power": float(bi.power) if hasattr(bi, "power") else 0,
                "direction": str(bi.direction),
                "sdt": str(bi.sdt), "edt": str(bi.edt),
            })

        return {
            "bi_list": bi_list,
            "bi_count": len(bi_list),
            "last_direction": bi_list[-1]["direction"] if bi_list else "unknown",
        }
