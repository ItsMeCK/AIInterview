from app import create_app

app = create_app()

if __name__ == '__main__':
    # Setting debug=True is not recommended for production
    app.run(debug=True, port=5001)