__author__ = 'Larry'

' url handlers '

from coroweb import get


@get('/')
async def index(request):
    return '<h1>Awesome</h1>'


@get('/hello')
async def hello(request):
    return '<h1>hello!</h1>'
