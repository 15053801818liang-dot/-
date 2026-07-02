"""自定义异常"""


class NotLeaderError(Exception):
    """当前节点不是 Leader"""
    pass
