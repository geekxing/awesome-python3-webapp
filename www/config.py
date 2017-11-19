"""
Configuration
"""


__author__ = 'Larry'

import config_default


class Dict(dict):
    """
    Simple dict but support access as x.y style.
    """
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attributes '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value


def merge(defaults, override):
    r = {}
    for k, v in defaults.items():
        if k in override:
            if isinstance(v, dict):
                r[k] = merge(v, override[k])  # 若v是dict，继续迭代
            else:
                r[k] = override[k]  # 否则，用新值覆盖默认值
        else:
            r[k] = v  # 覆盖参数未定义时，仍使用默认参数
    return r


def to_dict(d):
    dic = Dict()
    for k, v in d.items():
        dic[k] = to_dict(v) if isinstance(v, dict) else v
    return dic


configs = config_default.configs


try:
    import config_override
    configs = merge(configs, config_override.configs)  # 获得组合后的configs，dict
except ImportError:
    pass

configs = to_dict(configs)  # 将configs组合成Dict类的实例，可以通过configs.k直接获取v
