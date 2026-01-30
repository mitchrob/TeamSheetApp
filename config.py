import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-me-for-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Custom config
    CSV_PATH = os.path.join(basedir, "GRFC_data.csv")
    ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
    ADMIN_PASS = os.environ.get('ADMIN_PASS', 'password')
