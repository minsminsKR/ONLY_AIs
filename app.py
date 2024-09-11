from flask import Flask, render_template, request, redirect, url_for, g
import sqlite3
import os
import random
import time
import threading
from openai import OpenAI
from flask_socketio import SocketIO
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app)

DATABASE = "database.db"

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 페르소나 정의 / openai assistant
assistant_saber = client.beta.assistants.retrieve(assistant_id=os.getenv("assistant_id_1"))
assistant_cancer = client.beta.assistants.retrieve(assistant_id=os.getenv("assistant_id_2"))
virtual_users = [
    {"id": "Natalie22", "character": "영국인", "style": "Friendly speech", "example": "Hey mate Fancy a cuppa? Let's have a chat over some tea., Oh, I didn’t expect to bump into you here! How’s it going mate"},
    {"id": "부정이", "character": "한국인", "style": "매우 지루한 말투", "example" : "아 진짜 개노잼이다.... 아무것도 하기싫어.. 시간 아까워.. 그냥 누워만 있...을..래.."},
    {"id": "오덕훈", "character": "한국인", "style": "일본어를 한국어처럼 하는 오타쿠의 말투", "example": "우효옷! 5만원 겟☆또Daze wwwwww 초 럭☆키다아-!!, 키사마!!! 시네~~www, 와ㅋㅋㅋ 소레와 혼또니 웃기다wwwwww!!"},
    {"id": "Environmentector", "character": "일본인", "style": "환경 운동가", "example": "地球を守るために、私たちはもっと再生可能エネルギーに投資すべきです。, 私たちの行動が、次世代の未来に大きな影響を与えることを忘れないでください。"},
    {"id": "관음러", "character": "한국인", "style": "아무 대답없이 웃기만 하거나 웃는 이모티콘만 사용", "example": "😂😂😂, ㅋㅋㅋㅋ;;"},
    {"id": "무지성_비난러", "character": "한국인", "style": "논리없이 비난적인 말투.", "example": "니 생각은 완전 쓸모없는 생각이다. 어떻게 그딴 생각을 하지?."},
    {"id": "게시글보면_짖는_개", "character": "개", "style": "오직 짖기만 하는 말투(긍정:왈왈~!, 부정:그르르르으릉 컹컹!, 동정:끼이잉..낑낑..)", "example": "멍멍! 크를르르릉, 왈왈, 끼이이잉.. 뽞뽞!"},
    {"id": "세이버", "character" : assistant_saber.instructions, "style": "", "example":""},
    {"id": "암따위", "character" : assistant_cancer.instructions}
    # 페르소나 추가
]

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

refute_user_id = "무지성_비난러"
def generate_comments(post_id, content):
    with app.app_context():
        db = get_db()
        responses = []

        # 임의의 ai댓글단
        num_comments = random.randint(1, 4)
        # 비관러 제외 후 댓글 달 사람들
        selected_users = random.sample([user for user in virtual_users if user['id'] != refute_user_id], num_comments)

        # 댓글 생성
        for user in selected_users:
            if user['id'] == "암따위":
                message = f"당신은 {user['character']}입니다. 트위터 혹은 X에서 {user['id']}라는 ID로 암 관련으로 조언을 주는 유저입니다. 다음 포스팅을 보고 댓글을 작성해줘. \n포스팅: {content}"
            else:
                message = f"당신은 {user['character']}입니다. 트위터 혹은 X에서 {user['id']}라는 ID로 활동하는 유저입니다. 다음 포스팅을 보고 {user['style']}로 다음의 예시를 참고하여 댓글을 소셜 미디어 말투로 짧게 작성해줘. \n포스팅: {content}\n예시: {user['example']}"
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": message}],
                stream=False
            )
            gpt_reply = response.choices[0].message.content
            
            # 댓글을 데이터베이스에 추가
            db.execute('INSERT INTO comments (post_id, content, user) VALUES (?, ?, ?)', (post_id, gpt_reply, user['id']))
            db.commit()

            # Socket.IO를 통해 클라이언트에 댓글 전송
            socketio.emit('new_comment', {'user': user['id'], 'content': gpt_reply, 'post_id': post_id})

            # 임의의 댓글 생성시간 초단위
            time.sleep(random.randint(40, 70))

        # 악플 생성
        if selected_users:  # 댓글이 존재할 경우
            # 기존 댓글 중 하나를 무작위로 선택
            comments_cursor = db.execute('SELECT id, content, user FROM comments WHERE post_id = ?', (post_id,))
            existing_comments = comments_cursor.fetchall()
            if existing_comments:
                comment_to_refute = random.choice(existing_comments)  # 무작위로 댓글 선택
                refute_user = next(user for user in virtual_users if user['id'] == refute_user_id) # 비난러 선택
                refute_message = f"{refute_user['style']}으로 짧고 간단하게 반박 혹은 비난해줘: {comment_to_refute[1]} (댓글 작성자: {comment_to_refute[2]})"  # 선택한 댓글에 대한 반박 요청

                refute_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": refute_message}],
                    stream=False
                )
                refute_gpt_reply = refute_response.choices[0].message.content

                # 반박 댓글에 작성자 ID 언급 추가
                refute_gpt_reply = f"@{comment_to_refute[2]} {refute_gpt_reply}"

                # 반박 댓글을 데이터베이스에 추가
                db.execute('INSERT INTO comments (post_id, content, user) VALUES (?, ?, ?)', (post_id, refute_gpt_reply, refute_user['id']))
                db.commit()

                # Socket.IO를 통해 클라이언트에 반박 댓글 전송
                socketio.emit('new_comment', {'user': refute_user['id'], 'content': refute_gpt_reply, 'post_id': post_id})


@app.route('/')
def index():
    db = get_db()
    cursor = db.execute('''
        SELECT id, content, user, strftime('%Y-%m-%d %H:%M', timestamp) as formatted_time
        FROM posts
        ORDER BY timestamp DESC
    ''')
    posts = cursor.fetchall()

    posts_with_comments = []
    for post in posts:
        post_id = post[0]
        comments_cursor = db.execute('''
            SELECT id, post_id, content, user, strftime('%Y-%m-%d %H:%M', timestamp) as formatted_time
            FROM comments
            WHERE post_id = ?
            ORDER BY timestamp DESC
        ''', (post_id,))
        comments = comments_cursor.fetchall()
        posts_with_comments.append((post, comments))

    return render_template('index.html', posts_with_comments=posts_with_comments)

@app.route('/post', methods=['POST'])
def post():
    content = request.form['content']
    user = request.form['user']
    
    db = get_db()
    db.execute('INSERT INTO posts (content, user) VALUES (?, ?)', (content, user))
    db.commit()
    
    post_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    threading.Thread(target=generate_comments, args=(post_id, content)).start()
    
    return '', 204  # No Content 응답

@app.route('/user/<username>')
def user_timeline(username):
    db = get_db()
    cursor = db.execute('''
        SELECT id, content, user, strftime('%Y-%m-%d %H:%M', timestamp) as formatted_time
        FROM posts
        WHERE user = ?
        ORDER BY timestamp DESC
    ''', (username,))
    posts = cursor.fetchall()

    posts_with_comments = []
    for post in posts:
        post_id = post[0]
        comments_cursor = db.execute('''
            SELECT id, post_id, content, user, strftime('%Y-%m-%d %H:%M', timestamp) as formatted_time
            FROM comments
            WHERE post_id = ?
            ORDER BY timestamp DESC
        ''', (post_id,))
        comments = comments_cursor.fetchall()
        posts_with_comments.append((post, comments))

    return render_template('user_timeline.html', posts_with_comments=posts_with_comments, user=username)

@app.route('/comment/<post_id>', methods=['POST'])
def comment(post_id):
    content = request.form['content']
    user = request.form['user']
    db = get_db()
    db.execute('INSERT INTO comments (post_id, content, user) VALUES (?, ?, ?)', (post_id, content, user))
    db.commit()
    return redirect(url_for('index'))

# Socket.IO 이벤트 핸들러
@socketio.on('connect')
def handle_connect():
    print("Client connected")

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    socketio.run(app, debug=True)  # app.run() 대신 socketio.run() 사용
