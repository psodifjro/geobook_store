from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    orders = db.relationship("Order", backref="user", lazy=True)
    notifications = db.relationship("Notification", backref="user", lazy=True)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(250), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(120), nullable=False)

    description = db.Column(db.Text, default="")
    cover_url = db.Column(db.String(500), default="")

    price_buy = db.Column(db.Integer, default=499)       # покупка (руб)
    price_rent_2w = db.Column(db.Integer, default=149)   # 2 недели
    price_rent_1m = db.Column(db.Integer, default=249)   # 1 месяц
    price_rent_3m = db.Column(db.Integer, default=449)   # 3 месяца

    status = db.Column(db.String(60), default="Активна")  # Активна/Снята/Новинка и т.п.
    available = db.Column(db.Boolean, default=True)       # доступна ли пользователям


class Order(db.Model):
    """
    order_type:
      - BUY
      - RENT_2W
      - RENT_1M
      - RENT_3M

    Для аренды заполняются start_date/end_date.
    Для покупки end_date = None.
    """
    id = db.Column(db.Integer, primary_key=True)

    order_type = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)

    is_active = db.Column(db.Boolean, default=True)  # для аренды — активна до конца

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)

    book = db.relationship("Book", lazy=True)


class Notification(db.Model):
    """
    Уведомления пользователю (для напоминаний об окончании аренды).
    """
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)