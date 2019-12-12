from flask import Flask, render_template, request, session, redirect, url_for, send_file
import os
import uuid
import hashlib
import pymysql.cursors
from functools import wraps
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super secret key"
IMAGES_DIR = os.path.join(os.getcwd(), "images")

connection = pymysql.connect(host="localhost",
                             user="root",
                             password="root",
                             db="finsta",
                             charset="utf8mb4",
                             port=8889,
                             cursorclass=pymysql.cursors.DictCursor,
                             autocommit=True)


def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not "username" in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return dec


@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("home"))
    return render_template("index.html")


@app.route("/home")
@login_required
def home():
    return render_template("home.html",
                           username=session["username"])  # not changed, but html has been. has not been ran


@app.route("/upload", methods=["GET"])
@login_required
def upload():  # upload an image. maybe not relevant. double check that. changed decent amount, query finds every group
    username = session["username"]
    query = "SELECT BelongTo.groupName, BelongTo.owner_username FROM BelongTo JOIN Friendgroup ON BelongTo.owner_username = Friendgroup.groupOwner AND BelongTo.groupName = Friendgroup.groupName WHERE BelongTo.member_username = %s"
    with connection.cursor() as cursor:
        cursor.execute(query, username)
    group = cursor.fetchall()

    return render_template("upload.html", groups=group)

@app.route("/manage_followers", methods=["GET", "POST"])
@login_required
def manage_followers():
    username = session["username"]

    if request.form:
        username_follower = request.form['user']
        accept = request.form['follow']
        if accept:
            query = "UPDATE follow SET followstatus = 1 WHERE username_followed = %s AND username_follower = %s"
        elif not accept:
            query = "DELETE FROM follow WHERE username_followed = %s AND username_follower = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (username, username_follower))
    print(request.form)
    query = "SELECT * FROM follow WHERE username_followed = %s AND followstatus = 0"
    with connection.cursor() as cursor:
        cursor.execute(query, username)
    follow_requests = cursor.fetchall()
    return render_template("manage_followers.html", username=username, active_follow_reqs=follow_requests)

@app.route("/create_friendgroup", methods=["GET", "POST"])
@login_required
def create_friendgroup():
    username = session["username"]
    error = ''
    if request.form:
        query = "SELECT groupName FROM friendgroup WHERE groupOwner = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, username)
        existing_groups = cursor.fetchall()
        group_name = request.form["friendgroup name"]
        desc = request.form["friendgroup desc"]
        try:
            query = "INSERT INTO friendgroup (groupOwner, groupName, description) VALUES (%s, %s, %s)"
            with connection.cursor() as cursor:
                cursor.execute(query, (username, group_name, desc))
        except pymysql.err.IntegrityError:
            error = "Error: That group already exists."
    return render_template("create_friendgroup.html", username=username, error=error)


@app.route("/imagesPoster", methods=["GET", "POST"])  # displays
@login_required
def imagesPoster():
    # print(session["username"])
    username = session["username"]
    posterData = request.form.to_dict()

    print(posterData)
    poster = posterData["poster"]

    query = "(SELECT photo.photoID FROM photo JOIN follow ON photo.photoPoster = Follow.username_followed WHERE photo.AllFollowers = 1 AND Follow.followstatus = 1 AND Follow.username_follower = %s) " \
            "UNION (SELECT SharedWith.photoID FROM SharedWith JOIN BelongTo ON (SharedWith.groupName = BelongTo.groupName AND SharedWith.groupOwner = belongto.owner_username) WHERE BelongTo.member_username = %s) " \
            "UNION (SELECT photo.photoID FROM photo WHERE photo.photoPoster = %s)"  # woo! find all photos

    with connection.cursor() as cursor:
        cursor.execute(query, (username, username, username))
    dataID2 = cursor.fetchall()  # liste of dicts cursor returns list of dictionaries

    # fix dataID
    dataID = []  # list of ev visible photo
    for i in dataID2:  #
        dict1 = {}
        id = i["photoID"]  # list of dicts

        query = "SELECT photoID FROM Photo WHERE photoPoster = %s AND photoID = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (poster, id))
        tuple = cursor.fetchall()
        if tuple:
            dict1["photoID"] = id
            dataID.append(dict1)

    return render_template("imagesPoster.html", imageID=dataID, username=username, poster=poster)


@app.route("/images", methods=["GET", "POST"])  # where it gets fucked
@login_required
def images():
    username = session["username"]

    query = "(SELECT photo.photoID FROM photo JOIN follow ON photo.photoPoster = Follow.username_followed WHERE photo.AllFollowers = 1 AND Follow.followstatus = 1 AND Follow.username_follower = %s) " \
            "UNION (SELECT SharedWith.photoID FROM SharedWith JOIN BelongTo ON (SharedWith.groupName = BelongTo.groupName AND SharedWith.groupOwner = belongto.owner_username) WHERE BelongTo.member_username = %s) " \
            "UNION (SELECT photo.photoID FROM photo WHERE photo.photoPoster = %s)"

    with connection.cursor() as cursor:
        cursor.execute(query, (username, username, username))

    dataID = cursor.fetchall()  # list of dic, list of res from query. list of dictionaries key = 'photoID', val = photoID
    output = ''

    for i in dataID:
        query = "SELECT commenter, comment, photoID FROM Comments WHERE photoID = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, i["photoID"])

        commentsData = cursor.fetchall()

        output += "Comments for photoID " + str(i["photoID"]) + ":|"
        for comment in commentsData:
            output += comment["commenter"] + " commented: '" + comment["comment"] + "'|"



    output = output.split('|')  # output ends up being a list

    #FEATURE 2 START
    #name of poster
    query = "SELECT firstName, lastName FROM Photo JOIN Person ON Person.username = Photo.photoPoster WHERE photoID = %s"
    names = []
    for i in dataID:  # getting metadata (?) for each photoID
        with connection.cursor() as cursor:
            cursor.execute(query, i["photoID"])

        nameData = cursor.fetchone()  # returns one row of nameData

        names.append(nameData["firstName"] + " " + nameData["lastName"])  # to output to screen



    # timestamp

    query = "SELECT postingdate FROM Photo WHERE photoID = %s"
    times = []
    for i in dataID:
        with connection.cursor() as cursor:
            cursor.execute(query, i["photoID"])

        timeData = cursor.fetchone()

        times.append(timeData["postingdate"])

    tagged = []
    # usernames, fname, lname of people tagged and tag.acceptedTag = true
    query = "SELECT username, firstname, lastname FROM Tagged NATURAL JOIN Person WHERE tagstatus = 1 AND photoID = %s"
    for i in dataID:

        with connection.cursor() as cursor:
            cursor.execute(query, i["photoID"])
        tuple = cursor.fetchall()
        stringtag = ''
        if tuple:
            stringtag = "Tagged users for the photo include: "
        for row in tuple:
            stringtag += "User " + row["username"] + " with name " + row["firstname"] + " " + row["lastname"] + ", "
        if tuple:
            stringtag = stringtag[:-2]
        tagged.append(stringtag)
    # username of likers and the rating given
    likes = []
    query = "SELECT username, rating FROM Likes WHERE photoID = %s"
    likestring = ''
    for i in dataID:
        likestring = ''
        with connection.cursor() as cursor:
            cursor.execute(query, i["photoID"])
        tuple = cursor.fetchall()

        if tuple:
            likestring = "Likes for the photo include: "
            for row in tuple:
                likestring += "User " + row["username"] + " with rating " + str(row["rating"]) + ", "
            likestring = likestring[:-2]

        likes.append(likestring)

    if request.form:
        print(request.form)
        if "post" in request.form:
            check = request.form["likeorcom"]
            # print(check)
            if check == "like":
                data = request.form  # returns dict of values that the user has input on the webpahe
                like = int(data["inputVal"])
                photo = int(data["photoID"])
                now = datetime.now()
                current_time = now.strftime("%Y-%d-%m %H:%M:%S")

                query = "INSERT INTO Likes (username, photoID, liketime, rating) VALUES (%s, %s, %s, %s)"
                with connection.cursor() as cursor:
                    cursor.execute(query, (username, photo, current_time, like))
            if check == "com":
                data = request.form  # returns dict of values that the user has input on the webpahe
                comment = data["inputVal"]
                photo = int(data["photoID"])
                query = "INSERT INTO Comments (photoID, commenter, comment) VALUES (%s, %s, %s)"
                with connection.cursor() as cursor:
                    cursor.execute(query, (photo, username, comment))
    return render_template("images.html", imageID=dataID, username=username, comment=output, names=names, times=times,
                           tags=tagged, likes=likes)


@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):  # irrelevant atm
    image_location = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(image_location):
        return send_file(image_location, mimetype="image/jpg")


@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


@app.route("/register", methods=["GET"])
def register():
    return render_template("register.html")


@app.route("/loginAuth", methods=["POST"])
def loginAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()

        with connection.cursor() as cursor:
            query = "SELECT * FROM person WHERE username = %s AND password = %s"
            cursor.execute(query, (username, plaintextPasword))
        data = cursor.fetchone()
        if data:
            session["username"] = username
            return redirect(url_for("home"))

        error = "Incorrect username or password."
        return render_template("login.html", error=error)

    error = "An unknown error has occurred. Please try again."
    return render_template("login.html", error=error)


@app.route("/registerAuth", methods=["POST"])
def registerAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        firstName = requestData["fname"]
        lastName = requestData["lname"]

        try:
            with connection.cursor() as cursor:
                query = "INSERT INTO person (username, password, firstName, lastName) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (username, hashedPassword, firstName, lastName))
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)


@app.route("/logout", methods=["GET"])
def logout():
    session.pop("username")
    return redirect("/")


@app.route("/uploadImage", methods=["POST"])
@login_required
def upload_image():
    if request.files:
        requestData = request.form  # gets all data inout from upload
        image_file = request.files.get("imageToUpload", "")  # file ext
        image_name = image_file.filename
        followers = requestData["allFollower"]  # 1 is yes, 0 is no
        caption = requestData["caption"]
        groupName = requestData["groupName"]
        groupOwner = requestData["groupOwner"]  # names from the requestData in html file

        username = session["username"]
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)

        query = "INSERT INTO photo (postingdate, filepath, photoPoster, allFollowers, caption) VALUES (%s, %s, %s, %s, %s)"
        with connection.cursor() as cursor:
            timeKey = time.strftime(
                '%Y-%m-%d %H:%M:%S')  # used as a way to get the photoID afterwards, as we assume one photo is uploaded at once
            cursor.execute(query, (time.strftime('%Y-%m-%d %H:%M:%S'), image_name, username, followers, caption))

        query = "SELECT photoID FROM Photo WHERE postingdate = %s"  # uses timestamp to get photoID
        with connection.cursor() as cursor:
            cursor.execute(query, timeKey)

        photoID = cursor.fetchone()["photoID"]  # only one photoID returned

        if not (groupOwner == "NULL" and groupName == "NULL"):  # to deal with later
            query = "INSERT INTO SharedWith (groupOwner, groupName, photoID) VALUES (%s, %s, %s)"  # inserts photo uploaded in upload images
            with connection.cursor() as cursor:
                print(groupOwner, groupName, photoID)
                cursor.execute(query, (groupOwner, groupName, photoID))
        message = "Image has been successfully uploaded. Return to home?"
        return render_template("upload.html", message=message)
    else:
        message = "Failed to upload image."
        return render_template("upload.html", message=message)


if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run()
