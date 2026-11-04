# -*- coding: utf-8 -*-
"""样例：可变默认参数 + 裸 except。"""


def add_item(item, bucket=[]):
    bucket.append(item)
    return bucket


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except:
        return ""
