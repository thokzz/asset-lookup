from flask import Blueprint, render_template

static_pages = Blueprint('static_pages', __name__)

@static_pages.route('/about')
def about():
    return render_template('static_pages/about.html')
