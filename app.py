import os
from datetime import datetime, timedelta

from flask import Flask, render_template, redirect, url_for, request, abort, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_required, login_user, logout_user, current_user

from apscheduler.schedulers.background import BackgroundScheduler

from models import db, User, Book, Order, Notification


app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///store.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


# --- Создание таблиц ---
with app.app_context():
    db.create_all()


# --- Автоматические напоминания об окончании аренды ---
def rental_reminder_job():
    """
    1) Находит активные аренды, у которых конец аренды близко (<= 2 дня),
       создаёт уведомление (если не создавали недавно).
    2) Находит просроченные аренды и делает их неактивными.
    """
    with app.app_context():
        now = datetime.utcnow()
        soon_border = now + timedelta(days=2)

        active_rentals = Order.query.filter(
            Order.is_active == True,
            Order.order_type.in_(["RENT_2W", "RENT_1M", "RENT_3M"]),
            Order.end_date.isnot(None)
        ).all()

        for r in active_rentals:
            # Просрочено — деактивируем
            if r.end_date < now:
                r.is_active = False
                db.session.add(r)
                continue

            # Скоро заканчивается — уведомление
            if now <= r.end_date <= soon_border:
                days_left = (r.end_date - now).days
                msg = f"Напоминание: аренда книги «{r.book.title}» заканчивается через {days_left} дн."

                # чтобы не спамить: проверим, было ли похожее уведомление за последние 24 часа
                recent = Notification.query.filter(
                    Notification.user_id == r.user_id,
                    Notification.message == msg,
                    Notification.created_at >= (now - timedelta(hours=24))
                ).first()

                if not recent:
                    n = Notification(user_id=r.user_id, message=msg)
                    db.session.add(n)

        db.session.commit()


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(rental_reminder_job, "interval", minutes=1)  # для демо можно 1 мин
scheduler.start()


# --- PUBLIC / USER ---
@app.route("/")
def index():
    # фильтры сортировки
    category = request.args.get("category", "").strip()
    author = request.args.get("author", "").strip()
    year = request.args.get("year", "").strip()

    q = Book.query.filter_by(available=True)

    if category:
        q = q.filter(Book.category == category)
    if author:
        q = q.filter(Book.author == author)
    if year.isdigit():
        q = q.filter(Book.year == int(year))

    books = q.order_by(Book.title.asc()).all()

    # списки для фильтров
    categories = [x[0] for x in db.session.query(Book.category).distinct().all()]
    authors = [x[0] for x in db.session.query(Book.author).distinct().all()]
    years = sorted([x[0] for x in db.session.query(Book.year).distinct().all()])

    return render_template(
        "index.html",
        books=books,
        categories=categories,
        authors=authors,
        years=years,
        selected={"category": category, "author": author, "year": year},
    )


@app.route("/book/<int:book_id>")
def book(book_id):
    b = Book.query.get_or_404(book_id)

    if not b.available and (not current_user.is_authenticated or not current_user.is_admin):
        abort(404)

    return render_template("book.html", b=b)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Заполните логин и пароль", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Пользователь уже существует", "danger")
            return redirect(url_for("register"))

        u = User(username=username, password=generate_password_hash(password), is_admin=False)
        db.session.add(u)
        db.session.commit()

        flash("Регистрация успешна! Теперь войдите.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        u = User.query.filter_by(username=username).first()
        if not u or not check_password_hash(u.password, password):
            flash("Неверный логин или пароль", "danger")
            return redirect(url_for("login"))

        login_user(u)
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


def rental_price_and_end(book: Book, order_type: str):
    now = datetime.utcnow()

    if order_type == "BUY":
        return book.price_buy, None

    if order_type == "RENT_2W":
        return book.price_rent_2w, now + timedelta(days=14)

    if order_type == "RENT_1M":
        return book.price_rent_1m, now + timedelta(days=30)

    if order_type == "RENT_3M":
        return book.price_rent_3m, now + timedelta(days=90)

    raise ValueError("Unknown order type")


@app.route("/buy/<int:book_id>", methods=["POST"])
@login_required
def buy(book_id):
    b = Book.query.get_or_404(book_id)
    if not b.available:
        flash("Книга сейчас недоступна", "danger")
        return redirect(url_for("book", book_id=book_id))

    order_type = request.form.get("type", "BUY")
    if order_type not in ["BUY", "RENT_2W", "RENT_1M", "RENT_3M"]:
        abort(400)

    price, end_date = rental_price_and_end(b, order_type)
    start_date = datetime.utcnow() if order_type != "BUY" else None

    o = Order(
        order_type=order_type,
        price=price,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
        user_id=current_user.id,
        book_id=b.id,
    )

    db.session.add(o)
    db.session.commit()

    flash("Операция успешно выполнена!", "success")
    return redirect(url_for("my"))


@app.route("/my")
@login_required
def my():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    return render_template("my.html", orders=orders, notes=notes)


@app.route("/notification/read/<int:nid>", methods=["POST"])
@login_required
def read_notification(nid):
    n = Notification.query.get_or_404(nid)
    if n.user_id != current_user.id:
        abort(403)
    n.is_read = True
    db.session.commit()
    return redirect(url_for("my"))


# --- ADMIN ---
@app.route("/admin")
@login_required
def admin_dashboard():
    admin_required()

    total_books = Book.query.count()
    total_users = User.query.count()
    active_rentals = Order.query.filter(
        Order.is_active == True,
        Order.order_type.in_(["RENT_2W", "RENT_1M", "RENT_3M"])
    ).count()

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_users=total_users,
        active_rentals=active_rentals,
    )


@app.route("/admin/books")
@login_required
def admin_books():
    admin_required()
    books = Book.query.order_by(Book.id.desc()).all()
    return render_template("admin_books.html", books=books)


@app.route("/admin/books/new", methods=["GET", "POST"])
@login_required
def admin_books_new():
    admin_required()

    if request.method == "POST":
        b = Book(
            title=request.form.get("title", "").strip(),
            author=request.form.get("author", "").strip(),
            year=int(request.form.get("year", "2000")),
            category=request.form.get("category", "").strip(),
            description=request.form.get("description", "").strip(),
            cover_url=request.form.get("cover_url", "").strip(),
            price_buy=int(request.form.get("price_buy", "499")),
            price_rent_2w=int(request.form.get("price_rent_2w", "149")),
            price_rent_1m=int(request.form.get("price_rent_1m", "249")),
            price_rent_3m=int(request.form.get("price_rent_3m", "449")),
            status=request.form.get("status", "Активна"),
            available=True if request.form.get("available") == "on" else False,
        )
        db.session.add(b)
        db.session.commit()

        flash("Книга добавлена", "success")
        return redirect(url_for("admin_books"))

    return render_template("admin_book_form.html", mode="create", b=None)


@app.route("/admin/books/edit/<int:book_id>", methods=["GET", "POST"])
@login_required
def admin_books_edit(book_id):
    admin_required()
    b = Book.query.get_or_404(book_id)

    if request.method == "POST":
        b.title = request.form.get("title", "").strip()
        b.author = request.form.get("author", "").strip()
        b.year = int(request.form.get("year", "2000"))
        b.category = request.form.get("category", "").strip()
        b.description = request.form.get("description", "").strip()
        b.cover_url = request.form.get("cover_url", "").strip()

        b.price_buy = int(request.form.get("price_buy", "499"))
        b.price_rent_2w = int(request.form.get("price_rent_2w", "149"))
        b.price_rent_1m = int(request.form.get("price_rent_1m", "249"))
        b.price_rent_3m = int(request.form.get("price_rent_3m", "449"))

        b.status = request.form.get("status", "Активна")
        b.available = True if request.form.get("available") == "on" else False

        db.session.commit()

        flash("Изменения сохранены", "success")
        return redirect(url_for("admin_books"))

    return render_template("admin_book_form.html", mode="edit", b=b)


@app.route("/admin/books/delete/<int:book_id>", methods=["POST"])
@login_required
def admin_books_delete(book_id):
    admin_required()
    b = Book.query.get_or_404(book_id)
    db.session.delete(b)
    db.session.commit()
    flash("Книга удалена", "success")
    return redirect(url_for("admin_books"))


@app.route("/admin/rentals")
@login_required
def admin_rentals():
    admin_required()
    rentals = Order.query.filter(
        Order.order_type.in_(["RENT_2W", "RENT_1M", "RENT_3M"])
    ).order_by(Order.created_at.desc()).all()
    return render_template("admin_rentals.html", rentals=rentals)


@app.route("/admin/remind/<int:order_id>", methods=["POST"])
@login_required
def admin_remind(order_id):
    admin_required()
    r = Order.query.get_or_404(order_id)
    if r.order_type not in ["RENT_2W", "RENT_1M", "RENT_3M"]:
        abort(400)

    msg = f"Администратор напоминает: аренда книги «{r.book.title}» скоро заканчивается."
    n = Notification(user_id=r.user_id, message=msg)
    db.session.add(n)
    db.session.commit()

    flash("Напоминание отправлено", "success")
    return redirect(url_for("admin_rentals"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)