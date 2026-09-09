import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import random
import re
import traceback
import os
import sys
from pathlib import Path

# 伪装浏览器请求头
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Accept-Encoding": "gzip, deflate",
}


def resource_path(relative_path):
    """ 获取资源文件的绝对路径，兼容 PyInstaller 打包 """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = Path(".").absolute()
    return Path(base_path) / relative_path


def get_user_data_dir():
    """ 获取用户数据目录，用于保存可修改文件（跨平台兼容） """
    app_name = "MessageBombingTool"
    if os.name == 'nt':
        user_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / app_name
    elif sys.platform == 'darwin':
        user_dir = Path.home() / 'Library' / 'Application Support' / app_name
    else:
        user_dir = Path.home() / '.local' / 'share' / app_name
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_file_path(filename):
    """ 获取用户目录下的文件路径，首次运行时从默认资源复制 """
    user_file = get_user_data_dir() / filename
    if not user_file.exists():
        default_file = resource_path(filename)
        if default_file.exists():
            import shutil
            shutil.copy2(default_file, user_file)
            print(f"✅ 首次运行，已复制默认文件: {filename}")
    return user_file


# 读取配置文件（从资源或用户目录）
citys_path = resource_path('citys.txt')
needs_path = resource_path('needs.txt')

try:
    with open(citys_path, encoding='utf-8') as f:
        citys = [line.strip() for line in f.readlines() if line.strip()]
except Exception as e:
    print(f"❌ 读取 citys.txt 失败: {e}")
    citys = []

try:
    with open(needs_path, encoding='utf-8') as f:
        needs = [line.strip() for line in f.readlines() if line.strip()]
except Exception as e:
    print(f"❌ 读取 needs.txt 失败: {e}")
    needs = []


def create_session():
    """创建带重试机制的 requests Session"""
    session = requests.Session()
    session.headers.update(headers)
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def baidu_search(v_keyword, v_max_page, output_file):
    """
    爬取百度搜索结果并追加写入文件
    :param v_keyword: 搜索关键词
    :param v_max_page: 爬取页数
    :param output_file: 输出文件路径（Path 对象）
    :return: None
    """
    session = create_session()
    seen_links = set()

    # 先访问百度首页获取初始 Cookie
    try:
        session.get("https://www.baidu.com/", timeout=10)
    except requests.RequestException:
        pass

    for page in range(v_max_page):
        print(f'开始爬取第 {page + 1} 页')
        wait_seconds = random.uniform(2, 4)
        print(f'等待 {wait_seconds:.2f} 秒')
        time.sleep(wait_seconds)

        url = f'https://www.baidu.com/s?wd={v_keyword}&pn={page * 10}'
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            html = r.text

            # 提取 ada.baidu.com/site/ 开头的链接（兼容多种 URL 格式）
            links = re.findall(r'https?://ada\.baidu\.com/site/[^\s"\'<>]+', html)
            valid_links = []
            for link in links:
                # 去除尾部可能的 HTML 实体或多余字符
                link = link.rstrip('&amp;').rstrip(';')
                # 去重
                if link in seen_links:
                    continue
                seen_links.add(link)
                # 过滤 xyl.imid 开头的
                path_parts = link.split('/')
                if len(path_parts) >= 6 and not path_parts[5].startswith('xyl'):
                    valid_links.append(link)

            # 写入用户文件
            with open(output_file, 'a', encoding='utf-8') as f:
                for link in valid_links:
                    print(link)
                    f.write(link.strip() + '\n')

            print(f'第 {page + 1} 页获取到 {len(valid_links)} 个新链接')

        except requests.RequestException as e:
            print(f"请求失败: {e}")
        except Exception as e:
            traceback.print_exc()

    session.close()


def star_get_putian_url(stop_event=None, output_file=None):
    """
    主函数：爬取莆田系医院链接
    :param stop_event: threading.Event() 用于停止
    :param output_file: 输出文件路径，可选
    """
    if output_file is None:
        output_file = get_user_file_path('api.txt')

    # 清空文件（首次）
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            pass
        print(f"✅ 已清空输出文件: {output_file}")
    except Exception as e:
        print(f"❌ 无法清空文件: {e}")
        return

    for city in citys:
        for need in needs:
            if stop_event and stop_event.is_set():
                print("🛑 用户请求停止爬取。")
                return

            search_keyword = f"{city}{need}"
            print(f"🔍 搜索关键词: {search_keyword}")
            try:
                baidu_search(v_keyword=search_keyword, v_max_page=1, output_file=output_file)
            except Exception as e:
                print(f"❌ 搜索出错: {search_keyword}, 错误: {e}")
                traceback.print_exc()
                time.sleep(60)  # 避免频繁请求


if __name__ == '__main__':
    star_get_putian_url()