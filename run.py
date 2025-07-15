from app import create_app
from flask import Flask, render_template, session

app = create_app()

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html', 
                         username=session.get('username'), 
                         user_avatar=session.get('avatar_url')), 404

if __name__ == "__main__":
    app.run(debug=True)
