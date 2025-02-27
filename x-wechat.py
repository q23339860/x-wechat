import time
import time
from datetime import datetime, timezone, timedelta
import requests
import json
import csv
import os
import logging
from dotenv import load_dotenv
from urllib.parse import quote
import schedule
import threading
from openai import OpenAI

# 加载环境变量
load_dotenv()


client = OpenAI(
    api_key=os.environ.get("GPT_API_SK"),
    base_url=os.getenv("GPT_API_URL", "https://api.openai.com/v1")
)
# 环境变量配置
WECHAT_CORP_ID = os.environ.get("WECHAT_CORP_ID")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")
WECHAT_USER_ID = os.environ.get("WECHAT_USER_ID")
WECHAT_AGENT_ID = os.environ.get("WECHAT_AGENT_ID")

TWITTER_API_HOST = os.environ.get("TWITTER_API_HOST")
TWITTER_API_SK = os.environ.get("TWITTER_API_SK")

# 日志配置
log_dir = 'logs'

if not os.path.exists(log_dir):
    os.makedirs(log_dir)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{log_dir}/twitter_monitor_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def translate_text(text):
    MAX_TRANSLATE_LENGTH = 2000  # 假设翻译服务限制为2000字符
    if len(text) > MAX_TRANSLATE_LENGTH:
        logging.warning(f"文本长度超过翻译服务限制，已截断。原始长度: {len(text)}")
        text = text[:MAX_TRANSLATE_LENGTH]

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一名翻译助手，将推文翻译为中文，并保留原始英文。若遇到无法翻译的内容例如网址则保持原文。保持:'原文:*******\n 翻译:*******\n'的结构"},
                {"role": "user", "content": f"请翻译以下内容，并保留原始英文。若遇到无法翻译的内容例如网址则保持原文。保持:'原文:*******\n 翻译:*******\n'的结构：\n{text}"}
            ]
        )
        translated_content = response.choices[0].message.content
        print(translated_content)
        return translated_content
    except Exception as e:
        logging.warning(f"翻译出错: {str(e)}")
        return text  # 返回原始文本
def get_wechat_access_token():
    """获取企业微信Access Token"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECHAT_CORP_ID}&corpsecret={WECHAT_APP_SECRET}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get("errcode") == 0:
            return data.get("access_token")
        else:
            logging.error(f"获取企业微信访问令牌失败: {data.get('errmsg')}")
    else:
        logging.error(f"获取企业微信访问令牌失败: {response.json()}")
    return None

def send_wechat_message(content, media_ids):
    """发送企业微信消息"""
    access_token = get_wechat_access_token()
    if not access_token:
        logging.error("无法获取企业微信访问令牌")
        return

    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    if media_ids:
        payload = {
            "touser": WECHAT_USER_ID,
            "msgtype": "text",
            "agentid": WECHAT_AGENT_ID,
            "text": {"content": content},
            "safe": 0
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("errcode") == 0:
                logging.info(f"企业微信消息推送成功: {data}")
        
            else:
                logging.error(f"企业微信消息推送失败: {data.get('errmsg')}")
            
        else:
            logging.error(f"企业微信消息推送失败: {response.json()}")
        for media_id in media_ids:
            payload[media_id] = {
        "touser": WECHAT_USER_ID,
        "msgtype": "image",
        "agentid": WECHAT_AGENT_ID,
        "image": {
            "media_id": media_id
        },
        "safe": 0
        }   
            response2 = requests.post(url, json=payload[media_id])
            if response2.status_code == 200:
                data = response2.json()
                if data.get("errcode") == 0:
                    logging.info(f"图片消息推送成功: {data}")
        
                else:
                    logging.error(f"图片消息推送失败: {data.get('errmsg')}")
            
            else:
                logging.error(f"图片消息推送失败: {response.json()}")
    else:
        payload = {
            "touser": WECHAT_USER_ID,
            "msgtype": "text",
            "agentid": WECHAT_AGENT_ID,
            "text": {"content": content},
            "safe": 0
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("errcode") == 0:
                logging.info(f"企业微信消息推送成功: {data}")
        
            else:
                logging.error(f"企业微信消息推送失败: {data.get('errmsg')}")
            
        else:
            logging.error(f"企业微信消息推送失败: {response.json()}")
        

def process_tweet(tweet):
    """处理推文内容，提取文本和媒体"""
    if not isinstance(tweet, dict):
        logging.error(f"推文数据格式错误，不是字典类型: {tweet}")
        return "推文格式错误", []

    text = tweet.get('text', '无内容')
    media_urls = []

    # 检查推文是否包含媒体信息
    if 'media' in tweet:
        media = tweet['media']
        if media:  # 检查 media 是否为空
            if isinstance(media, list):  # 如果 media 是一个列表
                for item in media:
                    if isinstance(item, dict):
                        # 处理 photo 和 video 字段
                        if 'media_url_https' in item:
                            media_url = item.get('media_url_https')
                            if media_url:
                                media_urls.append(media_url)
                        elif 'media_url' in item:
                            media_url = item.get('media_url')
                            if media_url:
                                media_urls.append(media_url)
                        else:
                            logging.warning(f"未识别的媒体格式: {item}")
            elif isinstance(media, dict):  # 如果 media 是一个字典
                # 处理 photo 和 video 字段
                if 'photo' in media:
                    photos = media['photo']
                    if isinstance(photos, list):  # 如果 photo 是一个列表
                        for photo in photos:
                            if isinstance(photo, dict) and 'media_url_https' in photo:
                                media_url = photo.get('media_url_https')
                                if media_url:
                                    media_urls.append(media_url)
                    elif isinstance(photos, dict):  # 如果 photo 是一个字典
                        media_url = photos.get('media_url_https')
                        if media_url:
                            media_urls.append(media_url)
                    else:
                        logging.warning(f"未识别的媒体格式: {photos}")

                if 'video' in media:
                    videos = media['video']
                    if isinstance(videos, list):  # 如果 video 是一个列表
                        for video in videos:
                            if isinstance(video, dict) and 'media_url_https' in video:
                                media_url = video.get('media_url_https')
                                if media_url:
                                    media_urls.append(media_url)
                    elif isinstance(videos, dict):  # 如果 video 是一个字典
                        media_url = videos.get('media_url_https')
                        if media_url:
                            media_urls.append(media_url)
                    else:
                        logging.warning(f"未识别的媒体格式: {videos}")
            else:
                logging.warning(f"未识别的媒体格式: {media}")
        else:
            logging.info("媒体字段为空，跳过处理。")
    else:
        logging.info("推文不包含媒体信息。")

    return text, media_urls
def download_media(media_url, save_path, timeout=10):
    """
    下载媒体文件并保存到指定路径。
    :param media_url: 媒体文件的 URL。
    :param save_path: 保存文件的路径。
    :param timeout: 请求超时时间（秒）。
    :return: 如果下载成功，返回保存路径；否则返回 None。
    """
    try:
        # 发起请求并设置超时时间
        with requests.get(media_url, stream=True, timeout=timeout) as response:
            if response.status_code == 200:
                # 确保文件夹存在
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                # 以二进制写入模式打开文件
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:  # 过滤掉保持连接的新块
                            f.write(chunk)
                logging.info(f"下载成功: {media_url} -> {save_path}")
                return save_path
            else:
                logging.error(f"下载失败，状态码: {response.status_code}，URL: {media_url}")
    except requests.exceptions.Timeout:
        logging.error(f"请求超时: {media_url}")
    except requests.exceptions.RequestException as e:
        logging.error(f"请求异常: {str(e)}")
        logging.warning(f"如果需要解析链接 {media_url}，请检查链接的合法性，并适当重试。如果问题仍然存在，可能是网络问题导致的。")
    except Exception as e:
        logging.error(f"下载媒体时出错: {str(e)}")
    return None

def upload_media_to_wechat(file_path, access_token):
    """上传媒体文件到企业微信并返回媒体 ID"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={access_token}&type=image"
    with open(file_path, 'rb') as f:
        files = {'media': f}
        response = requests.post(url, files=files)
        if response.status_code == 200:
            data = response.json()
            if data.get("errcode") == 0:
                return data.get("media_id")
            else:
                logging.error(f"上传媒体文件失败: {data.get('errmsg')}")
        else:
            logging.error(f"上传媒体文件失败: {response.json()}")
    return None


def get_latest_tweets(screen_name, last_check_time):
    """获取用户最新推文"""
    logging.info(f"正在获取 {screen_name} 的最新推文...")
    encoded_screen_name = quote(screen_name)
    url = f"https://{TWITTER_API_HOST}/api/v1/twitter/web/fetch_user_post_tweet?screen_name={encoded_screen_name}&limit=50"
    headers = {'Authorization': f'Bearer {TWITTER_API_SK}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            logging.error(f"请求失败，状态码: {response.status_code}, 响应内容: {response.text}")
            return []
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logging.error(f"解析 JSON 失败: {e}, 响应内容: {response.text}")
            return []

        new_tweets = []
        if isinstance(data, dict) and 'data' in data and 'timeline' in data['data']:
            tweets = data['data']['timeline']
            for tweet in tweets:
                created_at = tweet.get('created_at')
                if created_at:
                    tweet_time = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=timezone.utc)
                    if tweet_time > last_check_time:
                        # 检查是否为转推
                        if 'retweeted_tweet' in tweet:
                            # 如果是转推，获取 retweeted_tweet 的内容
                            tweet_text = tweet.get('text')
                            retweet_text = tweet['retweeted_tweet'].get('text')
                            tweet['text'] = f"{tweet_text}\nRT @{tweet['retweeted_tweet']['author'].get('name')}:\n{retweet_text}"
                        else:
                            # 如果不是转推，直接获取原始推文内容
                            tweet_text = tweet.get('text', '无内容')

                        # 检查是否为回复
                        if tweet.get('quotes')!=0:
                            logging.info(f"跳过回复推文: {tweet['tweet_id']}")
                            continue

                        new_tweets.append(tweet)

        if new_tweets:
            logging.info(f"发现 {len(new_tweets)} 条新推文")
        else:
            logging.info("没有发现新推文")
        return new_tweets
    except requests.RequestException as e:
        logging.error(f"请求异常: {e}")
        return []



# 初始化缓存文件
CACHE_FILE = "tweets_cache.json"

def load_cache():
    """加载缓存文件"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    """保存缓存文件"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)

def monitor_tweets():
    """监控推特更新"""
    logging.info("开始初始化推特监控...")

    # 从 ID.csv 中读取用户信息
    with open('ID.csv', 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        creators = [(row['screen_name'], row['chinese_name']) for row in csv_reader]

    # 加载缓存
    cache = load_cache()

    # 初始化 last_check_time 和已处理推文 ID
    creator_last_tweets = {
        screen_name: {
            "last_check_time": datetime.now(timezone.utc) - timedelta(days=1),
            "processed_tweets": set(cache.get(screen_name, []))
        }
        for screen_name, _ in creators
    }

    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"[{current_time}] 正在检查更新...")

    for screen_name, chinese_name in creators:
        last_check_time = creator_last_tweets[screen_name]["last_check_time"]
        processed_tweets = creator_last_tweets[screen_name]["processed_tweets"]
        new_tweets = get_latest_tweets(screen_name, last_check_time)

        if new_tweets:
            logging.info(f"发现新推文，用户: {screen_name}")
            max_tweet_time = last_check_time  # 用于记录本轮检查的最大时间戳

            # 收集所有新推文
            tweets_to_save = []

            for tweet in new_tweets:
                tweet_id = tweet.get('tweet_id')

                if not tweet_id:
                    logging.warning(f"推文 ID 为空，跳过该推文: {tweet}")
                    continue

                if tweet_id in processed_tweets:
                    logging.info(f"跳过已处理的推文: {tweet_id}")
                    continue

                try:
                    tweet_time = datetime.strptime(tweet['created_at'], "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=timezone.utc)
                    max_tweet_time = max(max_tweet_time, tweet_time)  # 更新本轮最大时间戳

                    # 处理推文内容
                    text, media_urls = process_tweet(tweet)

                    # 翻译文本
                    translated_text = translate_text(text)

                    media_ids = []
                    for media_url in media_urls:
                        media_path = download_media(media_url, f"./media/{os.path.basename(media_url)}")
                        if media_path:
                            media_id = upload_media_to_wechat(media_path, get_wechat_access_token())
                            if media_id:
                                media_ids.append(media_id)

                    beijing_time = tweet_time.astimezone(timezone(timedelta(hours=8)))
                    created_at = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
                    message = f"🔔 {chinese_name} 发布新推文：\n发布时间: {created_at}\n内容: {translated_text}"
                    send_wechat_message(message, media_ids if media_ids else None)

                    logging.info(f"已推送推特: {tweet['created_at']} - {translated_text[:30]}...")

                    # 将推文加入保存列表
                    tweets_to_save.append(tweet)

                except Exception as e:
                    logging.error(f"处理推文时发生异常: {e}")
                finally:
                    processed_tweets.add(tweet_id)  # 记录已处理的推文 ID
                    creator_last_tweets[screen_name]["last_check_time"] = max_tweet_time  # 更新时间戳

            # 保存所有新推文到文件
            if tweets_to_save:
                file_name = save_tweets(tweets_to_save, screen_name)
                logging.info(f"推文数据已保存到文件: {file_name}")

        # 更新缓存
        cache[screen_name] = list(creator_last_tweets[screen_name]["processed_tweets"])
        save_cache(cache)

        # 每个用户之间的延时
        time.sleep(2)

    logging.info("推特监控结束。")
def save_tweets(tweets, screen_name):
    """保存推特数据到本地文件"""
    today = datetime.now().strftime("%Y%m%d")
    file_name = f"tweets/{screen_name}_{today}.json"
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, "a", encoding="utf-8") as f:
        for tweet in tweets:
            json.dump(tweet, f, ensure_ascii=False)
            f.write("\n")
    return file_name

def generate_summary():
    """生成并推送推特要闻总结"""
    logging.info("开始生成推特要闻总结...")
    summaries = generate_summary_from_tweets()
    if summaries:
        for summary in summaries:
            send_summary_to_wechat(summary)
    else:
        logging.warning("未生成有效的总结内容")


def generate_summary_from_tweets():
    """从保存的推特数据中生成总结"""
    tweet_dir = "tweets"
    if not os.path.exists(tweet_dir):
        logging.warning(f"推特文件夹不存在，无法生成总结: {tweet_dir}")
        return "今日暂无推特更新"

    # 扫描文件夹中的所有文件
    tweets_by_user = {}  # 用于按用户分组存储推文
    for filename in os.listdir(tweet_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(tweet_dir, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    tweet = json.loads(line)
                    # 提取用户信息
                    user = tweet.get("author", {}).get("name")
                    if not user:
                        logging.warning(f"推文缺少用户信息，跳过该推文: {tweet}")
                        continue

                    # 按用户分组存储推文
                    if user not in tweets_by_user:
                        tweets_by_user[user] = []
                    tweets_by_user[user].append(tweet)

    if not tweets_by_user:
        logging.warning("未找到任何推特数据，无法生成总结")
        return "今日暂无推特更新"

    # 为每个用户生成总结
    summaries = []
    for user, tweets in tweets_by_user.items():
        summary = summarize_with_chatgpt(tweets, user)
        summaries.append(summary)
    return summaries

def summarize_with_chatgpt(tweets, user):
    # 提取推文文本
    texts = [tweet.get("text", "") for tweet in tweets]
    summary_text = "\n".join(texts)
    
    # 如果文本过长，截断以避免超过 ChatGPT 输入限制
    if len(summary_text) > 10000:
        summary_text = summary_text[:10000]

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一名总结助手，必须以中文总结，按照不同推特总结为'用户:user发了:\n1、...\n2、...\n3、...'。将以下推特内容总结为要点："},
                {"role": "user", "content": f"用户: {user}\n推文内容:\n{summary_text}"}
            ]
        )
        summary = response.choices[0].message.content
        return summary
    except Exception as e:
        logging.error(f"ChatGPT 总结失败: {e}")
        return f"用户: {user} 的总结无法生成"


def send_summary_to_wechat(summary):
    """将总结内容推送到企业微信"""
    message = f"【推特要闻总结】\n{summary}"
    send_wechat_message(message,media_ids=None)


def cleanup_tweets():
    """清理旧的推特文件"""
    logging.info("开始清理旧的推特文件...")
    tweet_dir = "tweets"
    if not os.path.exists(tweet_dir):
        logging.warning(f"推特文件夹不存在，无需清理: {tweet_dir}")
        return

    # 获取前一天18:00的时间戳
    yesterday_1800 = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    yesterday_1800_timestamp = yesterday_1800.timestamp()

    # 删除前一天18:00之前的推特文件
    for filename in os.listdir(tweet_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(tweet_dir, filename)
            try:
                # 获取文件的最后修改时间（以时间戳形式）
                file_mtime = os.path.getmtime(file_path)

                # 如果文件的最后修改时间早于前一天18:00，则删除该文件
                if file_mtime < yesterday_1800_timestamp:
                    os.remove(file_path)
                    logging.info(f"已删除旧推特文件: {file_path}")
            except Exception as e:
                logging.error(f"清理推特文件时发生错误: {e} (文件名: {filename})")
def clear_cache():
    """清除缓存"""
    logging.info("清除缓存...")
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    logging.info("缓存已清除")


def clean_media_folder(folder_path, days_to_keep=7):
    """
    清理指定文件夹中的文件，删除超过指定天数的文件。
    :param folder_path: 要清理的文件夹路径。
    :param days_to_keep: 保留文件的天数。
    """
    if not os.path.exists(folder_path):
        logging.warning(f"文件夹不存在: {folder_path}")
        return

    now = datetime.now()
    cutoff_time = now - timedelta(days=days_to_keep)

    logging.info(f"开始清理文件夹: {folder_path}")
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime < cutoff_time:
                    os.remove(file_path)
                    logging.info(f"已删除文件: {file_path}")
            except Exception as e:
                logging.error(f"处理文件时出错: {file_path}, 错误: {str(e)}")
    logging.info(f"清理完成: {folder_path}")

def delete_cache_scheduler():
    schedule.every(7).days.at("00:30").do(clear_cache)

    logging.info("定时清理任务已启动...")
    while True:
        schedule.run_pending()
        time.sleep(1)
    
def monitor_scheduler():
    """运行定时任务"""
    logging.info("定时任务已启动...")
    schedule.every().day.at("03:00").do(monitor_tweets)
    schedule.every().day.at("06:00").do(monitor_tweets)
    schedule.every().day.at("09:00").do(monitor_tweets)
    schedule.every().day.at("12:00").do(monitor_tweets)
    schedule.every().day.at("15:00").do(monitor_tweets)
    schedule.every().day.at("18:00").do(monitor_tweets)
    schedule.every().day.at("21:00").do(monitor_tweets)
    schedule.every().day.at("00:00").do(monitor_tweets)
    """定时清理任务"""
    media_folder = "./media"  # 替换为你的 media 文件夹路径
    days_to_keep = 7  # 保留 7 天内的文件

    # 添加定时任务
    schedule.every().day.at("00:30").do(clean_media_folder, folder_path=media_folder, days_to_keep=days_to_keep)
    while True:
        schedule.run_pending()
        time.sleep(1)
def summary_scheduler():
    """运行定时任务，生成推特总结"""
    logging.info("定时任务已启动，每天1800点生成推特总结...")
    schedule.every().day.at("18:00").do(generate_summary)
    schedule.every().day.at("18:30").do(cleanup_tweets)
    while True:
        schedule.run_pending()
        time.sleep(1)
def main_scheduler():
    """主定时任务调度器"""
    logging.info("定时任务已启动...")

    # 添加定时任务
    schedule.every().day.at("01:19").do(monitor_tweets)
    schedule.every().day.at("06:00").do(monitor_tweets)
    schedule.every().day.at("09:00").do(monitor_tweets)
    schedule.every().day.at("12:00").do(monitor_tweets)
    schedule.every().day.at("15:00").do(monitor_tweets)
    schedule.every().day.at("18:00").do(monitor_tweets)
    schedule.every().day.at("21:00").do(monitor_tweets)
    schedule.every().day.at("00:00").do(monitor_tweets)

    # 定时清理任务
    media_folder = "./media"  # 替换为你的 media 文件夹路径
    days_to_keep = 7  # 保留 7 天内的文件

    # 添加定时任务
    schedule.every().day.at("00:30").do(clean_media_folder, folder_path=media_folder, days_to_keep=days_to_keep)
    schedule.every(7).days.at("00:30").do(clear_cache)

    # 定时生成推特总结
    schedule.every().day.at("18:00").do(generate_summary)
    schedule.every().day.at("18:30").do(cleanup_tweets)

    while True:
        schedule.run_pending()
        time.sleep(1)
if __name__ == "__main__":
    # 启动定时任务线程
    scheduler_thread = threading.Thread(target=main_scheduler, daemon=True)
    scheduler_thread.start()

    # 主线程保持运行
    while True:
        time.sleep(1)