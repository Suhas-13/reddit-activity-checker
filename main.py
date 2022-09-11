'''
example run:
python v3.py --subreddit giftcardexchange --target BigBen2010
'''

import praw
import json
import time
import os
import argparse
from itertools import chain

parser = argparse.ArgumentParser(description='Checks activity for users posting/commenting on subreddit')
parser.add_argument('--subreddit', metavar='s', type=str, nargs='+',
                    help='the name of the subreddit to be processed')
parser.add_argument('--target', metavar='t', type=str, nargs='+',
                    help='the name of the user/subreddit to be sent alerts')

args = parser.parse_args()

reddit = praw.Reddit(client_id='',
                            client_secret='',
                            username='',
                            password='',
                            user_agent='bot by hacksorskill')

submission_log_name = "ActivityCheckSubmission.txt"
comment_log_name = "ActivityCheckComment.txt"
last_processed_file_name = "LastProcessedTimes.json"
REPORT_TARGET_USER = reddit.redditor(args.target[0])

if not os.path.isfile(submission_log_name):
    with open(submission_log_name, "a+") as f:
        f.write("")
if not os.path.isfile(comment_log_name):
    with open(comment_log_name, "a+") as f:
        f.write("")
if not os.path.isfile(last_processed_file_name):
    with open(last_processed_file_name, "a+") as f:
        f.write("")        

unprocessed_data = open(last_processed_file_name).read()
if unprocessed_data == '':
    unprocessed_data = '{}'

last_processed_for_user = json.loads(unprocessed_data)

subreddit = reddit.subreddit(args.subreddit[0])

MAX_DAYS_BETWEEN_CHECKS = 15
MAX_TIME_DELAY = MAX_DAYS_BETWEEN_CHECKS * 24 * 60 * 60 
NUM_MONTHS_TO_CHECK = 2
SECONDS_PER_MONTH = 31*24*60*60 
SECONDS_PER_DAY = 24 * 60 * 60
MAX_POSTS_TO_CHECK = 150
MAX_DAYS_BETWEEN_POSTS = 15
MAX_TIME_BETWEEN_POSTS = 60 * 60 * 24 * MAX_DAYS_BETWEEN_POSTS
CHECK_FREQUENCY = 60 * 60 

last_check = time.time()

def download_approved():
    approved = set()
    for user in subreddit.contributor(limit=None):
        approved.add(user.name)
    return approved


def get_exchanges(flair_text):
    if flair_text is None or flair_text == "GCX Beginner":
        poster_exchanges = 0
    elif " Exchange" in flair_text:
        poster_exchanges = int(flair_text.split(" Exchange")[0].strip())
    return poster_exchanges


def check_user(author, approved, post):
    if author in last_processed_for_user and time.time() - last_processed_for_user[author] < MAX_TIME_DELAY:
        return True
    elif author in approved:
        return True
    
    # note this will only have the flair if the user has set the flair to show. 
    # doing exhaustive check would require many requests
    is_reply = False
    user_flair = post.author_flair_text
    if post.fullname.startswith("t1_"):
        is_reply = True
    poster_exchanges = get_exchanges(user_flair)
    if poster_exchanges > 20:
        return True
    if is_reply and post.submission:
        original_poster_flair = post.submission.author_flair_text
        original_poster_exchanges = get_exchanges(original_poster_flair)
        if abs(original_poster_exchanges - poster_exchanges) >= 8:
            return True
        
    timings_list = []
    pinned_posts_count = 0
    author_redditor = reddit.redditor(author)
    submissions = author_redditor.submissions.new(limit = MAX_POSTS_TO_CHECK)
    comments =  author_redditor.comments.new(limit = MAX_POSTS_TO_CHECK)
    
    for submission in submissions:
        if time.time() - submission.created_utc <= (SECONDS_PER_MONTH * NUM_MONTHS_TO_CHECK):
            timings_list.append(submission.created_utc)
        elif pinned_posts_count >= 5: # reddit allows a max of 4 pinned posts on a user's profile
            break
        else:
            pinned_posts_count+=1

    for comment in comments:
        if time.time() - comment.created_utc <= (SECONDS_PER_MONTH * NUM_MONTHS_TO_CHECK):
            timings_list.append(comment.created_utc)
        else:
            break
    

    if len(timings_list) == 0:
        return False
        
    if len(timings_list) < MAX_POSTS_TO_CHECK - 1:
        timings_list.append(time.time() - (NUM_MONTHS_TO_CHECK * SECONDS_PER_MONTH))
        timings_list.append(time.time())
        
    timings_list.sort()

    for i in range(1, len(timings_list)):
        if timings_list[i] - timings_list[i-1] >= MAX_TIME_BETWEEN_POSTS:
            return False
    return True



def process_user(author, post, last_processed_for_user, approved):
    if post.banned_by is not None or post.author is None:
        return
    if check_user(author, approved, post):
        last_processed_for_user[author] = time.time()
    else:
        if post.banned_by is not None or post.author is None:
            return
        print("Reporting " + author)
        global REPORT_TARGET_USER
        REPORT_TARGET_USER.message(subject = "u/" + author + " is inactive", message = "https://reddit.com" + str(post.permalink))
        
def main():
    try:
        approved = download_approved()
    except Exception as e:
        print(e)
    while True:
        try:
            with open(submission_log_name, "r+") as f:
                for submission in subreddit.stream.submissions(pause_after=-1):
                    if submission is None:
                        break
                    elif submission.created_utc < time.time()-400:
                        pass
                    elif submission.id not in f.read():
                        f.write(submission.id + "\n")
                        redditor = submission.author
                        author = redditor.name
                        process_user(author, submission, last_processed_for_user, approved)
                    f.seek(0)  
        except Exception as e:
            print("exception " + str(e))

        try:
            with open(comment_log_name, "r+") as f:
                for comment in subreddit.stream.comments(pause_after=-1):
                    if comment is None:
                        break
                    elif comment.created_utc < time.time()-400:
                        pass
                    elif comment.id not in f.read():
                        f.write(comment.id + "\n")   
                        redditor = comment.author
                        author = redditor.name
                        process_user(author, comment, last_processed_for_user, approved)    
                    f.seek(0)  
        except Exception as e:
            print("error " + str(e))
        
        try:
            with open(last_processed_file_name, "w") as f:
                json.dump(last_processed_for_user, f)

            if time.time() - CHECK_FREQUENCY > last_check:
                approved = download_approved()
        except Exception as e:
            print(e)


if __name__ == "__main__":
    main()