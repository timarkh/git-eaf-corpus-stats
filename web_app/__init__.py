from flask import Flask, request, after_this_request, render_template, session, jsonify,\
    current_app, send_from_directory, make_response, config
import json
from functools import wraps, update_wrapper
import os
from .corpus_stats import CorpusStats


SETTINGS_DIR = 'conf'
f = open(os.path.join(SETTINGS_DIR, 'corpora.json'), 'r', encoding='utf-8')
settings = json.loads(f.read())
f.close()
localizations = {}


def jsonp(func):
    """
    Wrap JSONified output for JSONP requests.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            data = str(func(*args, **kwargs).data)
            content = str(callback) + '(' + data + ')'
            mimetype = 'application/javascript'
            return current_app.response_class(content, mimetype=mimetype)
        else:
            return func(*args, **kwargs)
    return decorated_function


def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        # response.headers['Last-Modified'] = http_date(datetime.now())
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return update_wrapper(no_cache, view)


app = Flask(__name__)
app.secret_key = 'h6G3ff9(h5&kjgf%00'
app.config.update(dict(
    LANGUAGES=['ru', 'en'],
    BABEL_DEFAULT_LOCALE='ru'
))


def initialize_session():
    """
    Generate a unique session ID and initialize a dictionary with
    parameters for the current session. Write it to the global
    sessionData dictionary.
    """
    session['locale'] = app.config['BABEL_DEFAULT_LOCALE']


def get_locale():
    if 'locale' in session:
        return session['locale']
    initialize_session()
    return app.config['BABEL_DEFAULT_LOCALE']


@app.route('/set_locale/<lang>')
def set_locale(lang=''):
    if lang not in app.config['LANGUAGES']:
        return
    session['locale'] = lang
    return ''


@app.route('/')
def index_page():
    """
    If arguments are given, return HTML for a single question/topic.
    Otherwise, return HTML of the start page.
    """
    cs = CorpusStats(settings)
    return render_template('stats.html',
                           corpora=cs.corpora)
