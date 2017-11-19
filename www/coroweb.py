__author__ = 'Larry'


import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web


def get(path):
    """
    定义装饰器 @get('/path')
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator


def post(path):
    """
    定义装饰器 @post('/path')
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator


# 1.3 编写RequestHandler：处理request对象

# 1.3.1 解析视图函数

# param.kind 类型
# POSITIONAL_ONLY         = _POSITIONAL_ONLY
# POSITIONAL_OR_KEYWORD   = _POSITIONAL_OR_KEYWORD
# VAR_POSITIONAL          = _VAR_POSITIONAL
# KEYWORD_ONLY            = _KEYWORD_ONLY
# VAR_KEYWORD             = _VAR_KEYWORD
#
# empty = _empty

def get_required_kw_args(fn):  # 获取无默认值的命名关键词参数
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):  # 获取命名关键词参数
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):  # 判断是否有命名关键词参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_arg(fn):   # 判断是否有关键词参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_request_arg(fn):    # 判断是否含有名叫'request'的参数，且位置在最后
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (
            param.kind != inspect.Parameter.VAR_POSITIONAL and
            param.kind != inspect.Parameter.KEYWORD_ONLY and
            param.kind != inspect.Parameter.VAR_KEYWORD):
            # 若判断为True，表明param只能是位置参数。且该参数位于request之后，故不满足条件，报错。
            raise ValueError('request params must be the last named param in function: %s%s' % (fn.__name__, str(sig)))
    return found


# 1.3.2 提取request中的参数

# RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，
# 调用URL函数，然后把结果转换为web.Response对象，这样，就完全符合aiohttp框架的要求
class RequestHandler(object):

    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    # 1.定义kw，用于保存参数
    # 2.判断视图函数是否存在关键词参数，如果存在根据POST或者GET方法将request请求内容保存到kw
    # 3.如果kw为空（说明request无请求内容），则将match_info列表里的资源映射给kw；若不为空，把命名关键词参数内容给kw
    # 4.完善_has_request_arg和_required_kw_args属性
    async def __call__(self, request):
        kw = None  # 定义kw，用于保存request中参数
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:  # 若视图函数有命名关键词或关键词参数
            if request.method == 'POST':
                # 根据request参数中的content_type使用不同解析方法：
                if not request.content_type:  # 如果content_type不存在，返回400错误
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()  # 小写，便于检查
                if ct.startswith('application/json'):  # json格式数据
                    params = await request.json()  # request.json()返回dict对象
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                # form表单请求的编码形式
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()  # 返回post的内容中解析后的数据。dict-like对象。
                    kw = dict(**params)  # 组成dict，统一kw格式
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string   # 以string形式返回URL查询语句，?后的键值。
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():  # 返回查询变量和值的映射，dict对象。True表示不忽略空格。
                        kw[k] = v[0]
        if kw is None:
            # request.match_info返回dict对象。可变路由中的可变字段{variable}为参数名，传入request请求的path为值
            # 若存在可变路由：/a/{name}/c，可匹配path为：/a/jack/c的request
            # 则request.match_info返回{name = jack}
            kw = dict(**request.match_info)
        else:   # request有参数
            if not self._has_var_kw_arg and self._named_kw_args:  # 若视图函数只有命名关键词参数没有关键词参数
                copy = dict()
                # 只保留命名关键字参数
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy  # 现在kw中只存在命名关键词参数
            for k, v in request.match_info.items():
                # 检查kw中的参数是否和match_info中的重复
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:  # 视图函数存在request参数
            kw['request'] = request
        if self._required_kw_args:  # 视图函数存在无默认值的命名关键词参数
            for name in self._required_kw_args:
                if not name in kw:  # 若未传入必须参数值，报错。
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        # 至此，kw为视图函数fn真正能调用的参数
        # request请求中的参数，终于传递给了视图函数
        logging.info('call with args: %s' % str(kw))
        r = await self._func(**kw)
        return r


# 2.1 编写视图函数注册函数
# add_route函数功能：
# 1、验证视图函数是否拥有method和path参数
# 2、将视图函数转变为协程

# 编写一个add_route函数，用来注册一个视图函数
def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn, ', '.join(inspect.signature(fn).parameters.keys())))
    # 在app中注册经RequestHandler类封装的视图函数
    app.router.add_route(method, path, RequestHandler(app, fn))


# 导入模块，批量注册视图函数
def add_routes(app, module_name):
    n = module_name.rfind('.')  # 从右侧检索，返回索引。若无，返回-1。
    if n == (-1):
        # __import__ 作用同import语句，但__import__是一个函数，并且只接收字符串作为参数
        # __import__('os',globals(),locals(),['path','pip'], 0) ,等价于from os import path, pip
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n+1:]
        # 只获取最终导入的模块，为后续调用dir()
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):  # dir()迭代出mod模块中所有的类，实例及函数等对象,str形式
        if attr.startswith('_'):
            continue  # 忽略'_'开头的对象，直接继续for循环
        fn = getattr(mod, attr)
        # 确保是函数
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            # 确保视图函数存在method和path
            if method and path:
                # 注册
                add_route(app, fn)


# 2.2 编写静态文件注册函数
# 添加静态文件，如image，css，javascript等
def add_static(app):
    # 拼接static文件目录
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))

