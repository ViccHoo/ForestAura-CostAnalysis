from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import lru_cache
from datetime import datetime, timedelta
from sqlalchemy import func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forest_aura.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, default='其它')  # 产品类别
    purchase_cost = db.Column(db.Float, nullable=False)  # 单个商品的进货成本
    selling_price = db.Column(db.Float, nullable=False)  # 单个商品的售价
    inventory = db.Column(db.Integer, nullable=False, default=0)  # 当前库存
    total_sales = db.Column(db.Integer, nullable=False, default=0)  # 总销量
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    @property
    def total_revenue(self):
        """总收入"""
        return self.selling_price * self.total_sales
    
    @property
    def total_purchase_cost(self):
        """进货总成本"""
        return self.purchase_cost * self.total_sales
    
    @property
    def actual_profit(self):
        """实际利润（基于销量，仅考虑进货成本）"""
        return self.total_revenue - self.total_purchase_cost
    
    @property
    def profit_margin(self):
        """利润率（基于进货成本）"""
        if self.total_purchase_cost == 0:
            return 0
        return (self.actual_profit / self.total_purchase_cost) * 100
    
    @property
    def unit_profit(self):
        """单件商品的利润（仅考虑进货成本）"""
        return self.selling_price - self.purchase_cost
    
    @property
    def unit_profit_margin(self):
        """单件商品的利润率"""
        if self.purchase_cost == 0:
            return 0
        return ((self.selling_price - self.purchase_cost) / self.purchase_cost) * 100

class Cost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)  # 成本类别：运营成本、市场成本等
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    description = db.Column(db.Text, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_dashboard_data():
    # 获取产品统计
    product_stats = db.session.query(
        func.count(Product.id).label('total_products'),
        func.sum(Product.total_sales).label('total_sales'),
        func.sum(Product.inventory).label('total_inventory'),
        func.sum((Product.selling_price * Product.total_sales)).label('total_revenue'),
        func.sum((Product.purchase_cost * Product.total_sales)).label('total_purchase_cost')
    ).first()

    # 获取总运营成本
    total_operation_costs = db.session.query(
        func.sum(Cost.amount).label('total_costs')
    ).first()

    # 计算实际总利润（总收入 - 总进货成本 - 总运营成本）
    total_revenue = product_stats.total_revenue or 0
    total_purchase_cost = product_stats.total_purchase_cost or 0
    total_operation_cost = total_operation_costs.total_costs or 0
    actual_total_profit = total_revenue - total_purchase_cost - total_operation_cost

    # 按类别统计商品数量和销售情况
    products_by_category = db.session.query(
        Product.category,
        func.count(Product.id).label('count'),
        func.sum(Product.inventory).label('inventory'),
        func.sum(Product.total_sales).label('sales'),
        func.sum(Product.selling_price * Product.total_sales).label('revenue'),
        func.sum(Product.purchase_cost * Product.total_sales).label('cost')
    ).group_by(Product.category).all()

    # 获取成本统计
    cost_by_category = db.session.query(
        Cost.category,
        func.sum(Cost.amount).label('total_amount')
    ).group_by(Cost.category).all()

    # 获取最近添加的产品
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(5).all()

    # 获取销量最高的产品
    top_selling_products = Product.query.order_by(Product.total_sales.desc()).limit(5).all()

    # 获取利润最高的产品（考虑单品利润率）
    top_profit_products = Product.query.order_by(
        ((Product.selling_price - Product.purchase_cost) * Product.total_sales).desc()
    ).limit(5).all()

    # 计算总体利润率
    profit_margin = (actual_total_profit / total_purchase_cost * 100) if total_purchase_cost > 0 else 0

    # 扩展统计数据
    extended_stats = {
        'total_products': product_stats.total_products or 0,
        'total_sales': product_stats.total_sales or 0,
        'total_inventory': product_stats.total_inventory or 0,
        'total_revenue': total_revenue,
        'total_purchase_cost': total_purchase_cost,
        'total_operation_cost': total_operation_cost,
        'actual_total_profit': actual_total_profit,
        'profit_margin': profit_margin
    }

    return {
        'product_stats': extended_stats,
        'products_by_category': products_by_category,
        'cost_by_category': cost_by_category,
        'recent_products': recent_products,
        'top_selling_products': top_selling_products,
        'top_profit_products': top_profit_products
    }

@app.route('/')
@login_required
def index():
    dashboard_data = get_dashboard_data()
    return render_template('dashboard.html', data=dashboard_data)

@app.route('/products')
@login_required
def products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('products.html', products=products)

@app.route('/costs')
@login_required
def costs():
    costs = Cost.query.order_by(Cost.date.desc()).all()
    return render_template('costs.html', costs=costs)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        try:
            new_product = Product(
                name=request.form.get('name'),
                category=request.form.get('category'),
                purchase_cost=float(request.form.get('purchase_cost')),
                selling_price=float(request.form.get('selling_price')),
                inventory=int(request.form.get('inventory', 0))
            )
            db.session.add(new_product)
            db.session.commit()
            flash('商品添加成功！')
        except Exception as e:
            db.session.rollback()
            flash('添加商品失败，请重试！')
        return redirect(url_for('products'))
    return render_template('add_product.html')

@app.route('/add_cost', methods=['GET', 'POST'])
@login_required
def add_cost():
    if request.method == 'POST':
        try:
            new_cost = Cost(
                name=request.form.get('name'),
                category=request.form.get('category'),
                amount=float(request.form.get('amount')),
                date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
                description=request.form.get('description')
            )
            db.session.add(new_cost)
            db.session.commit()
            flash('成本记录添加成功！')
        except Exception as e:
            db.session.rollback()
            flash('添加成本记录失败，请重试！')
        return redirect(url_for('costs'))
    return render_template('add_cost.html')

@app.route('/delete_product/<int:id>')
@login_required
def delete_product(id):
    try:
        product = Product.query.get_or_404(id)
        db.session.delete(product)
        db.session.commit()
        flash('商品已删除！')
    except Exception as e:
        db.session.rollback()
        flash('删除商品失败，请重试！')
    return redirect(url_for('products'))

@app.route('/delete_cost/<int:id>')
@login_required
def delete_cost(id):
    try:
        cost = Cost.query.get_or_404(id)
        db.session.delete(cost)
        db.session.commit()
        flash('成本记录已删除！')
    except Exception as e:
        db.session.rollback()
        flash('删除成本记录失败，请重试！')
    return redirect(url_for('costs'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        user = User.query.first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('密码错误')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/update_inventory/<int:id>', methods=['POST'])
@login_required
def update_inventory(id):
    try:
        product = Product.query.get_or_404(id)
        action = request.form.get('action')
        amount = int(request.form.get('amount', 1))
        
        if action == 'add_inventory':
            product.inventory += amount
            flash(f'已添加 {amount} 件库存')
        elif action == 'reduce_inventory':
            if product.inventory >= amount:
                product.inventory -= amount
                product.total_sales += amount
                flash(f'已售出 {amount} 件商品')
            else:
                flash('库存不足！')
                return redirect(url_for('products'))
        elif action == 'adjust_sales':
            old_sales = product.total_sales
            new_sales = amount
            sales_diff = new_sales - old_sales
            
            if sales_diff > 0:  # 增加销量
                if product.inventory >= sales_diff:
                    product.inventory -= sales_diff
                    product.total_sales = new_sales
                    flash(f'销量已更新，增加了 {sales_diff} 件销售')
                else:
                    flash('库存不足，无法增加销量！')
                    return redirect(url_for('products'))
            else:  # 减少销量
                product.inventory -= sales_diff  # 减少负数相当于增加库存
                product.total_sales = new_sales
                flash(f'销量已更新，减少了 {-sales_diff} 件销售')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('操作失败，请重试！')
    return redirect(url_for('products'))

def init_db():
    with app.app_context():
        # 删除所有表
        db.drop_all()
        # 创建所有表
        db.create_all()
        # 创建默认用户
        if not User.query.first():
            user = User(
                username='admin',
                password_hash=generate_password_hash('301699')
            )
            db.session.add(user)
            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 