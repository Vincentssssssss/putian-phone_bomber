# boom.py - 核心自动化逻辑模块

import time
import random
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.by import By
import logging
import os
import sys
from pathlib import Path

# 配置日志（由 GUI 控制输出，这里只记录）
logger = logging.getLogger(__name__)


def resource_path(relative_path):
    """ 获取资源文件的绝对路径，兼容 PyInstaller 打包 """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = Path(".").absolute()
    return Path(base_path) / relative_path


def get_user_data_dir():
    """ 获取用户数据目录，用于保存可修改的配置文件（跨平台兼容） """
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
    """
    获取用户目录下的文件路径
    首次运行时从默认资源复制
    """
    user_file = get_user_data_dir() / filename
    if not user_file.exists():
        default_file = resource_path(filename)
        if default_file.exists():
            import shutil
            shutil.copy2(default_file, user_file)
            logger.info(f"✅ 首次运行，已复制默认文件: {filename}")
        else:
            raise FileNotFoundError(f"❌ 默认配置文件未找到: {filename}")
    return user_file


def load_selectors():
    """
    从 selectors.json 加载 CSS 选择器配置
    优先读取用户目录，其次读取项目目录
    """
    # 查找顺序：用户目录 > 项目目录
    search_paths = [
        get_user_data_dir() / 'selectors.json',
        resource_path('selectors.json'),
    ]

    for path in search_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"✅ 已加载选择器配置: {path}")
                return config
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"❌ 选择器配置文件损坏: {path}, {e}")

    # 如果都没找到，使用默认值（向后兼容）
    logger.warning("⚠️ 未找到 selectors.json，使用默认选择器")
    return {
        "input_box": {"by": "CLASS_NAME", "value": "pc-imlp-component-typebox-input"},
        "send_button": {"by": "CLASS_NAME", "value": "pc-imlp-component-typebox-send"},
        "wait_timeout_seconds": 10
    }


def get_by_enum(by_str):
    """将字符串转换为 Selenium By 枚举"""
    by_map = {
        "CLASS_NAME": By.CLASS_NAME,
        "CSS_SELECTOR": By.CSS_SELECTOR,
        "ID": By.ID,
        "NAME": By.NAME,
        "XPATH": By.XPATH,
        "TAG_NAME": By.TAG_NAME,
        "LINK_TEXT": By.LINK_TEXT,
        "PARTIAL_LINK_TEXT": By.PARTIAL_LINK_TEXT,
    }
    return by_map.get(by_str.upper(), By.CLASS_NAME)


def load_urls_from_file(custom_path=None):
    """
    从 api.txt 加载URL列表
    :param custom_path: 可选路径，优先使用
    """
    file_path = Path(custom_path) if custom_path else get_user_file_path('api.txt')

    if not file_path.exists():
        raise FileNotFoundError(f"❌ 缺少 api.txt 文件: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        raise ValueError("❌ api.txt 文件为空，请添加有效URL。")

    logger.info(f"✅ 已加载 {len(urls)} 个URL")
    return urls


def load_needCheat_from_file(custom_path=None):
    """
    从 need_cheat.txt 加载前缀列表
    :param custom_path: 可选路径
    """
    file_path = Path(custom_path) if custom_path else get_user_file_path('need_cheat.txt')

    if not file_path.exists():
        raise FileNotFoundError(f"❌ 缺少 need_cheat.txt 文件: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        needs = [line.strip() for line in f if line.strip()]

    if not needs:
        raise ValueError("❌ need_cheat.txt 文件为空，请添加有效前缀。")

    logger.info(f"✅ 已加载 {len(needs)} 个前缀")
    return needs


def find_chrome_path():
    """
    自动检测 Chrome 浏览器路径（跨平台）
    :return: Chrome 路径，未找到返回 None
    """
    import glob
    candidates = []
    if os.name == 'nt':
        # Windows
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(Path(os.getenv('LOCALAPPDATA', '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'),
        ]
    elif sys.platform == 'darwin':
        # macOS
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            str(Path.home() / 'Applications' / 'Google Chrome.app' / 'Contents' / 'MacOS' / 'Google Chrome'),
        ]
    else:
        # Linux
        candidates = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/snap/bin/chromium',
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def create_driver(chrome_path=None):
    """创建带配置的Chrome浏览器实例"""
    if not chrome_path:
        chrome_path = find_chrome_path()
    if not chrome_path:
        raise FileNotFoundError(
            "❌ 未找到 Chrome 浏览器，请手动指定路径。\n"
            "  macOS: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
            "  Windows: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\n"
            "  Linux: /usr/bin/google-chrome"
        )
    options = Options()
    options.binary_location = chrome_path
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-logging")
    options.page_load_strategy = "eager"
    options.add_argument("--headless=new")  # 可选：无头模式
    options.add_argument('--log-level=3')
    return webdriver.Chrome(options=options)


def visit_website(chrome_path, phone, url, need_cheat, selectors=None):
    """
    单个访问任务
    :param chrome_path: Chrome可执行文件路径
    :param phone: 手机号
    :param url: 目标URL
    :param need_cheat: 前缀列表
    :param selectors: 选择器配置（可选，默认从 selectors.json 加载）
    :return: 是否成功
    """
    if selectors is None:
        selectors = load_selectors()

    driver = None
    try:
        driver = create_driver(chrome_path)
        timeout = selectors.get('wait_timeout_seconds', 10)
        wait = WebDriverWait(driver, timeout)

        # 先访问百度（防止某些网站拦截）
        driver.get("https://www.baidu.com/")
        time.sleep(0.5)
        driver.get(url)

        # 切换到最新窗口（如果有弹窗）
        handles = driver.window_handles
        if len(handles) > 1:
            driver.switch_to.window(handles[-1])

        # 随机选择前缀 + 手机号
        prefix = random.choice(need_cheat)
        message = prefix + phone

        # 从配置读取选择器
        input_cfg = selectors['input_box']
        send_cfg = selectors['send_button']

        # 输入并发送
        input_box = wait.until(EC.presence_of_element_located(
            (get_by_enum(input_cfg['by']), input_cfg['value'])
        ))
        input_box.clear()
        input_box.send_keys(message)

        send_btn = wait.until(EC.element_to_be_clickable(
            (get_by_enum(send_cfg['by']), send_cfg['value'])
        ))
        send_btn.click()

        time.sleep(1)  # 可视化延迟
        logger.info(f"✅ 成功发送: {url}")
        return True

    except Exception as e:
        logger.error(f"❌ 访问失败 {url}: {e}")
        return False

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass  # 忽略关闭异常


def diagnose(url, chrome_path=None):
    """
    诊断模式：访问目标 URL，分析页面 DOM 结构，
    帮助找到正确的输入框和发送按钮选择器。
    :param url: 目标医院 ADA 页面 URL
    :param chrome_path: Chrome 路径（可选）
    """
    print(f"\n🔍 诊断模式启动，正在访问: {url}")
    print("=" * 60)

    driver = None
    try:
        driver = create_driver(chrome_path)
        driver.get("https://www.baidu.com/")
        time.sleep(0.5)
        driver.get(url)

        # 等待页面加载
        time.sleep(5)

        # 切换窗口
        handles = driver.window_handles
        if len(handles) > 1:
            driver.switch_to.window(handles[-1])
            print(f"📌 已切换到最新窗口 (共 {len(handles)} 个)")

        time.sleep(3)  # 等待聊天组件加载

        print("\n📋 页面中的所有 input/textarea 元素:")
        print("-" * 60)
        inputs = driver.find_elements(By.TAG_NAME, 'input')
        textareas = driver.find_elements(By.TAG_NAME, 'textarea')
        all_fields = inputs + textareas

        if not all_fields:
            print("  ❌ 未找到任何 input/textarea 元素")
            print("  💡 可能原因：页面未完全加载 / 聊天组件在 iframe 中")
        else:
            for i, elem in enumerate(all_fields):
                tag = elem.tag_name
                cls = elem.get_attribute('class') or '(无)'
                elem_id = elem.get_attribute('id') or '(无)'
                name = elem.get_attribute('name') or '(无)'
                placeholder = elem.get_attribute('placeholder') or '(无)'
                visible = elem.is_displayed()
                print(f"  [{i}] <{tag}>")
                print(f"      class: {cls}")
                print(f"      id: {elem_id}")
                print(f"      name: {name}")
                print(f"      placeholder: {placeholder}")
                print(f"      可见: {visible}")
                print()

        print("\n📋 页面中所有 button 元素:")
        print("-" * 60)
        buttons = driver.find_elements(By.TAG_NAME, 'button')
        # 也找 div/span 带 role="button" 的
        role_buttons = driver.find_elements(By.CSS_SELECTOR, '[role="button"]')
        # 找包含"发送"文字的任意元素
        send_elements = driver.find_elements(By.XPATH, '//*[contains(text(), "发送")]')

        all_btns = buttons + role_buttons + send_elements
        seen = set()
        for i, elem in enumerate(all_btns):
            elem_id = id(elem)
            if elem_id in seen:
                continue
            seen.add(elem_id)
            tag = elem.tag_name
            cls = elem.get_attribute('class') or '(无)'
            text = (elem.text or '').strip()[:50]
            elem_id_attr = elem.get_attribute('id') or '(无)'
            visible = elem.is_displayed()
            print(f"  [{i}] <{tag}>")
            print(f"      class: {cls}")
            print(f"      id: {elem_id_attr}")
            print(f"      text: {text}")
            print(f"      可见: {visible}")
            print()

        if not all_btns:
            print("  ❌ 未找到任何 button 元素")

        # 检查 iframe
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        if iframes:
            print(f"\n⚠️ 页面包含 {len(iframes)} 个 iframe，聊天组件可能在 iframe 中")
            print("  💡 如果是这样，需要切换到 iframe 后再查找元素")

        # 当前选择器测试
        print("\n🧪 测试当前 selectors.json 中的选择器:")
        print("-" * 60)
        selectors = load_selectors()
        input_cfg = selectors['input_box']
        send_cfg = selectors['send_button']

        try:
            elem = driver.find_element(get_by_enum(input_cfg['by']), input_cfg['value'])
            print(f"  ✅ 输入框 [{input_cfg['by']}={input_cfg['value']}] → 找到！")
        except Exception:
            print(f"  ❌ 输入框 [{input_cfg['by']}={input_cfg['value']}] → 未找到")

        try:
            elem = driver.find_element(get_by_enum(send_cfg['by']), send_cfg['value'])
            print(f"  ✅ 发送按钮 [{send_cfg['by']}={send_cfg['value']}] → 找到！")
        except Exception:
            print(f"  ❌ 发送按钮 [{send_cfg['by']}={send_cfg['value']}] → 未找到")

        print("\n" + "=" * 60)
        print("💡 如果选择器失效，请从上面的列表中找到正确的 class/id")
        print("   然后更新 selectors.json 文件中的 value 字段")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def boom(chrome_path, phone, max_workers=5, url_file=None, cheat_file=None):
    """
    主执行函数
    :param chrome_path: Chrome路径
    :param phone: 手机号
    :param max_workers: 最大并发数
    :param url_file: 自定义 api.txt 路径（可选）
    :param cheat_file: 自定义 need_cheat.txt 路径（可选）
    """
    try:
        # 使用传入路径或默认用户路径
        urls = load_urls_from_file(url_file)
        need_cheat = load_needCheat_from_file(cheat_file)
        total = len(urls)

        logger.info(f"🚀 开始任务：共 {total} 个链接，最大并发数: {max_workers}")

        success_count = 0
        failed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(visit_website, chrome_path, phone, url, need_cheat): url
                for url in urls
            }

            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    if future.result():
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as exc:
                    logger.error(f"任务异常 {url}: {exc}")
                    failed_count += 1

        logger.info(f"🎉 所有任务完成！成功: {success_count} | 失败: {failed_count}")
        return True

    except Exception as e:
        logger.error(f"💣 任务中断: {e}")
        return False


if __name__ == '__main__':
    # 诊断模式: python main.py --diagnose <url> [chrome_path]
    if len(sys.argv) >= 3 and sys.argv[1] == '--diagnose':
        target_url = sys.argv[2]
        chrome = sys.argv[3] if len(sys.argv) > 3 else None
        diagnose(target_url, chrome)
    else:
        print("用法:")
        print("  诊断模式:  python main.py --diagnose <url> [chrome_path]")
        print("  示例:      python main.py --diagnose https://ada.baidu.com/site/xxx")
        print()
        print("  通过 GUI 启动: python gui.py")