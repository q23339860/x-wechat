import time
from datetime import datetime, timezone, timedelta
import requests
import json
import csv
import os
import logging
from dotenv import load_dotenv
from urllib.parse import quote

# 加载环境变量
load_dotenv()

# 环境变量配置
WECHAT_CORP_ID = os.environ.get("WECHAT_CORP_ID")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")
WECHAT_USER_ID = os.environ.get("WECHAT_USER_ID")
WECHAT_AGENT_ID = os.environ.get("WECHAT_AGENT_ID")

TWITTER_API_HOST = os.environ.get("TWITTER_API_HOST")
TWITTER_API_SK = os.environ.get("TWITTER_API_SK")

GPT_API_URL = os.environ.get("GPT_API_URL")  
GPT_API_SK = os.environ.get("GPT_API_SK")

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
def is_chinese(text):
    """检查文本是否包含中文"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

def translate_text(text):
    """使用 GPT API 翻译文本，仅翻译英文内容"""
    if is_chinese(text):
        return text

    url = GPT_API_URL
    headers = {
        "Authorization": f"Bearer {GPT_API_SK}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": "你是一名翻译助手，将推文翻译为中文，并保留原始英文。"
            },
            {
                "role": "user",
                "content": f"请翻译以下内容,并保留原始英文：\n{text}"
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            return f"翻译失败 (HTTP {response.status_code})"
    except Exception as e:
        return f"翻译出错: {str(e)}"
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

def send_wechat_message(content, media_ids=None):
    """发送企业微信消息"""
    access_token = get_wechat_access_token()
    if not access_token:
        logging.error("无法获取企业微信访问令牌")
        return

    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    if media_ids:
        payload = {
            "touser": WECHAT_USER_ID,
            "msgtype": "news",
            "agentid": WECHAT_AGENT_ID,
            "news": {
                "articles": [
                    {
                        "title": "推特更新",
                        "description": content,
                        "url": "http://example.com",  # 替换为实际链接
                        "picurl": media_ids[0] if media_ids else "",  # 使用第一张图片作为封面
                        "btntxt": "阅读全文"
                    }
                ]
            },
            "safe": 0
        }
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
        if isinstance(media, list):  # 如果 media 是一个列表
            for item in media:
                if isinstance(item, dict) and 'media_url' in item:
                    media_url = item.get('media_url')
                    if media_url:
                        media_urls.append(media_url)
        elif isinstance(media, dict):  # 如果 media 是一个字典
            media_url = media.get('media_url')
            if media_url:
                media_urls.append(media_url)
        else:
            logging.warning(f"未识别的媒体格式: {media}")

    return text, media_urls

def download_media(media_url, save_path):
    """下载媒体文件"""
    try:
        response = requests.get(media_url, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            logging.info(f"下载成功: {media_url}")
            return save_path
        else:
            logging.error(f"下载失败: {media_url}")
    except Exception as e:
        logging.error(f"下载媒体时出错: {str(e)}")
    return None

def upload_media_to_wechat(file_path, access_token):
    """上传媒体文件到企业微信"""
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
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        logging.error(f"请求失败，状态码: {response.status}, 响应内容: {response.text}")
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
                    new_tweets.append(tweet)
    if new_tweets:
        logging.info(f"发现 {len(new_tweets)} 条新推文")
    else:
        logging.info("没有发现新推文")
    return new_tweets


def monitor_tweets():
    """监控推特更新"""
    logging.info("开始初始化推特监控...")

    # 从 ID.csv 中读取用户信息
    with open('ID.csv', 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        creators = [(row['screen_name'], row['chinese_name']) for row in csv_reader]

    # 初始化 last_check_time 为当前时间
    creator_last_tweets = {screen_name: datetime.now(timezone.utc) - timedelta(days=1) for screen_name, _ in creators}

    logging.info(f"开始监控推特更新，当前时间: {datetime.now(timezone.utc)}")

    while True:
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"[{current_time}] 正在检查更新...")

        for screen_name, chinese_name in creators:
            last_check_time = creator_last_tweets[screen_name]
            new_tweets = get_latest_tweets(screen_name, last_check_time)

            if new_tweets:
                logging.info(f"发现新推文，用户: {screen_name}")
                for tweet in new_tweets:
                    tweet_time = datetime.strptime(tweet['created_at'], "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=timezone.utc)
                    creator_last_tweets[screen_name] = tweet_time

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
                    if media_ids:
                        send_wechat_message(message, media_ids)
                    else:
                        send_wechat_message(message)

                    logging.info(f"已推送推特: {tweet['created_at']} - {translated_text[:30]}...")

                    # 立即更新 last_check_time，避免重复推送
                    creator_last_tweets[screen_name] = tweet_time

                    # 每处理完一条推特后暂停，确保实时性
                    time.sleep(2)

            # 每个用户之间的延时
            time.sleep(2)

        # 每次循环结束后暂停，等待下一次检查
        time.sleep(10800)  # 每 3 小时检查一次

if __name__ == "__main__":
    monitor_tweets() 