__author__ = 'Larry'

' url handlers '

import re, time, hashlib, json, logging

import markdown2

from aiohttp import web

from coroweb import get, post
from apis import APIError, APIValueError, APIResourceNotFoundError, APIPermissionError, Page

from models import User, Blog, Comment, next_id
from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()


def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


def user2cookie(user, max_age):
    '''
    Generate cookie str by user
    '''
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    cookie_comps = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(cookie_comps)


def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid
    '''
    if not cookie_str:
        return None
    try:
        cookie_comps = cookie_str.split('-')
        if len(cookie_comps) != 3:
            return None
        uid, expires, sha1 = cookie_comps
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


@get('/')
async def index(request, *, page='1'):
    """ 首页 """
    # 视图函数返回的值是dict
    page_index = get_page_index(page)
    num = await Blog.findnumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        blogs = []
    blogs = await Blog.findall(orgerBy='created_at desc', limit=(p.offset, p.limit))
    return {
        # 在response_middleware中会搜索模板
        '__template__': 'blogs.html',
        'page': p,
        'blogs': blogs,
        '__user__': request.__user__
    }


@get('/blog/{id}')
async def get_blog(id, request):
    """ 日志详情页 """
    blog = await Blog.find(id)
    comments = await Comment.findall('blog_id=?', [id], orgerBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments,
        '__user__': request.__user__
    }


@get('/register')
async def register():
    """ 注册页 """
    return {
        '__template__': 'register.html'
    }


@get('/signin')
async def signin():
    """ 登录页 """
    return {
        '__template__': 'signin.html'
    }


@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findall('email=?', [email])
    if len(users) == 0:
        raise APIError('email', 'Email not exists.')
    user = users[0]
    # check passwd
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/signout')
async def signout(request):
    """ 注销页 """
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r


@get('/manage/')
def manage():
    return 'redirect:/manage/comments'


@get('/manage/comments')
async def manage_comments(request, *, page='1'):
    """ 日志列表页 """
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page),
        '__user__': request.__user__
    }


@get('/manage/blogs')
async def manage_blogs(request, *, page='1'):
    """ 日志列表页 """
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page),
        '__user__': request.__user__
    }


@get('/manage/blogs/create')
async def manage_create_blog(request):
    """ 创建日志页 """
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs',
        '__user__': request.__user__
    }


@get('/manage/blogs/edit')
async def manage_edit_blog(request, *, id):
    """ 修改日志页 """
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id,
        '__user__': request.__user__
    }


@get('/manage/users')
async def manage_users(request, *, page='1'):
    """ 用户列表页 """
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page),
        '__user__': request.__user__
    }


@get('/api/comments')
async def api_comments(*, page='1'):
    """ 获取评论 """
    page_index = get_page_index(page)
    num = await Comment.findnumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    blogs = await Comment.findall(orgerBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=blogs)


@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    """ 创建评论 """
    user = request.__user__
    if user is None:
        raise APIPermissionError('please signin first.')
    if not content or not content.strip():
        raise APIValueError('content', 'content can not be empty.')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    await comment.save()
    return comment


@post('/api/comments/{id}/delete')
async def api_delete_comment(id, request):
    """ 删除评论 """
    check_admin(request)
    comment = await Comment.find(id)
    if comment is None:
        raise APIResourceNotFoundError('Comment')
    await comment.remove()
    return dict(id=id)


@get('/api/users')
async def api_get_users(*, page='1'):
    """ 获取用户 """
    page_index = get_page_index(page)
    num = await User.findnumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findall(orgerBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, users=users)
    for u in users:
        u.passwd = '******'
    return dict(users=users)


_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


@post('/api/users')
async def api_register_user(*, email, name, passwd):
    """ 创建新用户 """
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findall('email=?',[email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/api/blogs')
async def api_blogs(*, page='1'):
    """ 获取日志 """
    page_index = get_page_index(page)
    num = await Blog.findnumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findall(orgerBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


@get('/api/blog/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog


@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    """ 创建日志 """
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name can not be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary can not be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content can not be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
                name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog


@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):
    """ 修改日志 """
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name can not be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary can not be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content can not be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog


@post('/api/blogs/{id}/delete')
async def api_delete_blog(id, request):
    """ 删除日志 """
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)
