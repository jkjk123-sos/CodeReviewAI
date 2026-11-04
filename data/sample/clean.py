"""样例：干净文件，用来验证退出码 0。"""


def add_item(item, bucket=None):
    bucket = bucket or []
    bucket.append(item)
    return bucket
