"""缠论主引擎 — 背驰检测"""
from czsc import CZSC


class ChanlunEngine:
    def run(self, bars: list, duan_result: dict = None) -> dict:
        if duan_result is None or duan_result.get("bi_count", 0) < 3:
            return self._empty("insufficient data")

        try:
            c = CZSC(bars, max_bi_num=500)
        except Exception as e:
            return {"error": str(e), "signals": []}

        signals = self._detect_divergence(c)

        return {
            "signals": signals,
            "bi_count": duan_result.get("bi_count", 0),
            "last_direction": duan_result.get("last_direction", "?"),
            "latest_price": float(c.bars_raw[-1].close) if c.bars_raw else 0,
        }

    def _detect_divergence(self, c: CZSC) -> list:
        """比较同方向最近的两笔：价格新高/新低但力度衰减 → 背驰"""
        signals = []
        bi_list = c.bi_list
        if len(bi_list) < 3:
            return signals

        # 从当前位置向前找上一个同向笔
        for i in range(2, len(bi_list)):
            curr = bi_list[i]
            d_curr = str(curr.direction)
            c_power = float(curr.power) if hasattr(curr, "power") else 0
            c_high = float(curr.high)
            c_low = float(curr.low)

            # 向前追溯到最近的同向笔
            for j in range(i - 1, -1, -1):
                prev = bi_list[j]
                d_prev = str(prev.direction)
                if d_prev != d_curr:
                    continue  # skip opposite direction

                p_power = float(prev.power) if hasattr(prev, "power") else 0
                p_high = float(prev.high)
                p_low = float(prev.low)

                if d_curr == "向下":
                    if c_low < p_low and c_power < p_power * 0.90:
                        signals.append({
                            "type": "bottom_divergence",
                            "bi_index": i,
                            "price": round(c_low, 2),
                            "prev_power": round(p_power, 2),
                            "curr_power": round(c_power, 2),
                            "strength": round(1 - c_power / max(p_power, 0.0001), 3),
                        })
                elif d_curr == "向上":
                    if c_high > p_high and c_power < p_power * 0.90:
                        signals.append({
                            "type": "top_divergence",
                            "bi_index": i,
                            "price": round(c_high, 2),
                            "prev_power": round(p_power, 2),
                            "curr_power": round(c_power, 2),
                            "strength": round(1 - c_power / max(p_power, 0.0001), 3),
                        })
                break  # 只比较最近同向笔

        return signals

    @staticmethod
    def _empty(reason: str) -> dict:
        return {"signals": [], "error": reason, "bi_count": 0, "latest_price": 0}
