# -*- coding: utf-8 -*-
import pytest

from flask import Flask, url_for
from werkzeug.routing import BuildError
from werkzeug.wrappers import BaseResponse
from flask_marshmallow import Marshmallow
from flask_marshmallow.fields import _tpl

from flask_sqlalchemy import SQLAlchemy

import marshmallow

IS_MARSHMALLOW_2 = int(marshmallow.__version__.split('.')[0]) >= 2

_app = Flask(__name__)

@_app.route('/author/<int:id>')
def author(id):
    return 'Steven Pressfield'

@_app.route('/authors/')
def authors():
    return 'Steven Pressfield, Chuck Paluhniuk'

@_app.route('/books/')
def books():
    return 'Legend of Bagger Vance, Fight Club'

@_app.route('/books/<id>')
def book(id):
    return 'Legend of Bagger Vance'

mar = Marshmallow(_app)

@pytest.yield_fixture(scope='function')
def app():

    ctx = _app.test_request_context()
    ctx.push()

    yield _app

    ctx.pop()

@pytest.fixture(scope='function')
def ma(app):
    return Marshmallow(app)


class MockModel(dict):
    def __init__(self, *args, **kwargs):
        super(MockModel, self).__init__(*args, **kwargs)
        self.__dict__ = self

class Author(MockModel):
    pass

class Book(MockModel):
    pass

@pytest.fixture
def mockauthor():
    author = Author(id=123, name='Fred Douglass')
    return author

@pytest.fixture
def mockbook(mockauthor):
    book = Book(id=42, author=mockauthor, title='Legend of Bagger Vance')
    return book


@pytest.mark.parametrize('template', [
    '<id>',
    ' <id>',
    '<id> ',
    '< id>',
    '<id  >',
    '< id >',
])
def test_tpl(template):
    assert _tpl(template) == 'id'
    assert _tpl(template) == 'id'
    assert _tpl(template) == 'id'

def test_url_field(ma, mockauthor):
    field = ma.URLFor('author', id='<id>')
    result = field.serialize('url', mockauthor)
    assert result == url_for('author', id=mockauthor.id)

    mockauthor.id = 0
    result = field.serialize('url', mockauthor)
    assert result == url_for('author', id=0)

def test_url_field_with_invalid_attribute(ma, mockauthor):
    field = ma.URLFor('author', id='<not-an-attr>')
    with pytest.raises(AttributeError) as excinfo:
        field.serialize('url', mockauthor)
    expected_msg = '{0!r} is not a valid attribute of {1!r}'.format(
        'not-an-attr', mockauthor)
    assert expected_msg in str(excinfo)

def test_url_field_deserialization(ma):
    field = ma.URLFor('author', id='<not-an-attr>', allow_none=True)
    # noop
    assert field.deserialize('foo') == 'foo'
    assert field.deserialize(None) is None

def test_invalid_endpoint_raises_build_error(ma, mockauthor):
    field = ma.URLFor('badendpoint')
    with pytest.raises(BuildError):
        field.serialize('url', mockauthor)

def test_hyperlinks_field(ma, mockauthor):
    field = ma.Hyperlinks({
        'self': ma.URLFor('author', id='<id>'),
        'collection': ma.URLFor('authors')
    })

    result = field.serialize('_links', mockauthor)
    assert result == {
        'self': url_for('author', id=mockauthor.id),
        'collection': url_for('authors')
    }

def test_hyperlinks_field_recurses(ma, mockauthor):
    field = ma.Hyperlinks({
        'self': {
            'href': ma.URLFor('author', id='<id>'),
            'title': 'The author'
        },
        'collection': {
            'href': ma.URLFor('authors'),
            'title': 'Authors list'
        }
    })
    result = field.serialize('_links', mockauthor)

    assert result == {
        'self': {'href': url_for('author', id=mockauthor.id),
                'title': 'The author'},
        'collection': {'href': url_for('authors'),
                        'title': 'Authors list'}
    }


def test_hyperlinks_field_recurses_into_list(ma, mockauthor):
    field = ma.Hyperlinks([
        {'rel': 'self', 'href': ma.URLFor('author', id='<id>')},
        {'rel': 'collection', 'href': ma.URLFor('authors')}
    ])
    result = field.serialize('_links', mockauthor)

    assert result == [
        {'rel': 'self', 'href': url_for('author', id=mockauthor.id)},
        {'rel': 'collection', 'href': url_for('authors')}
    ]

def test_hyperlinks_field_deserialization(ma):
    field = ma.Hyperlinks({
        'href': ma.URLFor('author', id='<id>')
    }, allow_none=True)
    # noop
    assert field.deserialize('/author') == '/author'
    assert field.deserialize(None) is None

def test_absolute_url(ma, mockauthor):
    field = ma.AbsoluteURLFor('authors')
    result = field.serialize('abs_url', mockauthor)
    assert result == url_for('authors', _external=True)

def test_absolute_url_deserialization(ma):
    field = ma.AbsoluteURLFor('authors', allow_none=True)
    assert field.deserialize('foo') == 'foo'
    assert field.deserialize(None) is None

def test_deferred_initialization():
    app = Flask(__name__)
    m = Marshmallow()
    m.init_app(app)

    assert 'flask-marshmallow' in app.extensions

def test_aliases(ma):
    from flask_marshmallow.fields import UrlFor, AbsoluteUrlFor, URLFor, AbsoluteURLFor
    assert UrlFor is URLFor
    assert AbsoluteUrlFor is AbsoluteURLFor

class AuthorSchema(mar.Schema):
    class Meta:
        fields = ('id', 'name', 'absolute_url', 'links')

    absolute_url = mar.AbsoluteURLFor('author', id='<id>')

    links = mar.Hyperlinks({
        'self': mar.URLFor('author', id='<id>'),
        'collection': mar.URLFor('authors')
    })

class BookSchema(mar.Schema):
    class Meta:
        fields = ('id', 'title', 'author', 'links')

    author = mar.Nested(AuthorSchema)

    links = mar.Hyperlinks({
        'self': mar.URLFor('book', id='<id>'),
        'collection': mar.URLFor('books'),
    })

def test_schema(app, mockauthor):
    s = AuthorSchema()
    result = s.dump(mockauthor)
    assert result.data['id'] == mockauthor.id
    assert result.data['name'] == mockauthor.name
    assert result.data['absolute_url'] == url_for('author',
        id=mockauthor.id, _external=True)
    links = result.data['links']
    assert links['self'] == url_for('author', id=mockauthor.id)
    assert links['collection'] == url_for('authors')

def test_jsonify(app, mockauthor):
    s = AuthorSchema()
    resp = s.jsonify(mockauthor)
    assert isinstance(resp, BaseResponse)
    assert resp.content_type == 'application/json'

def test_links_within_nested_object(app, mockbook):
    s = BookSchema()
    result = s.dump(mockbook)
    assert result.data['title'] == mockbook.title
    author = result.data['author']
    assert author['links']['self'] == url_for('author', id=mockbook.author.id)
    assert author['links']['collection'] == url_for('authors')

class TestSQLAlchemy:

    @pytest.yield_fixture()
    def extapp(self):
        app_ = Flask('extapp')
        app_.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        SQLAlchemy(app_)
        Marshmallow(app_)
        ctx = _app.test_request_context()
        ctx.push()

        yield app_

        ctx.pop()

    @pytest.fixture()
    def db(self, extapp):
        return extapp.extensions['sqlalchemy'].db

    @pytest.fixture()
    def extma(self, extapp):
        return extapp.extensions['flask-marshmallow']

    @pytest.yield_fixture()
    def models(self, db):
        class AuthorModel(db.Model):
            __tablename__ = 'author'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(255))

        class BookModel(db.Model):
            __tablename__ = 'book'
            id = db.Column(db.Integer, primary_key=True)
            title = db.Column(db.String(255))
            author_id = db.Column(db.Integer, db.ForeignKey('author.id'))
            author = db.relationship('AuthorModel', backref='books')

        db.create_all()

        class _models:
            def __init__(self):
                self.Author = AuthorModel
                self.Book = BookModel
        yield _models()
        db.drop_all()

    def test_can_declare_model(self, extma, models, db):
        class AuthorSchema(extma.ModelSchema):
            class Meta:
                model = models.Author

        author_schema = AuthorSchema()

        author = models.Author(name='Chuck Paluhniuk')

        db.session.add(author)
        db.session.commit()
        result = author_schema.dump(author)
        assert 'id' in result.data
        assert 'name' in result.data
        assert result.data['name'] == 'Chuck Paluhniuk'

        resp = author_schema.jsonify(author)
        assert isinstance(resp, BaseResponse)
