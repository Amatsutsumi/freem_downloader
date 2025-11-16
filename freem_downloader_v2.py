import requests
from bs4 import BeautifulSoup
import os
import time
import re
from urllib.parse import urljoin
import logging
from tqdm import tqdm
import sys
import json
import subprocess

class FreemGameDownloader:
    def __init__(self, force_rescan=False):
        # ================= 配置区域 =================
        self.download_dir = ""
        self.status_dir = ""
        self.rclone_remote = ""
        # --- 登录账户信息 ---
        self.email = ""
        self.password = ""
        # ===========================================

        self.completed_log_file = os.path.join(self.status_dir, "completed_games.json")
        self.game_list_cache_file = os.path.join(self.status_dir, "game_list_cache.json")
        self.force_rescan = force_rescan

        self.base_url = "https://www.freem.ne.jp"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.status_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(self.status_dir, 'main.log'), encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # --- 【新增】在初始化时执行登录操作 ---
        if not self.login():
            self.logger.critical("登录失败，程序无法继续。请检查账户和密码。")
            sys.exit(1) # 登录失败则直接退出程序

    # ---------------------------------------------------------
    # 【全新】自动登录功能
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # 【最终修复版】自动登录功能
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # 【最终版】自动登录功能 (根据实际HTML重构)
    # ---------------------------------------------------------
    def login(self):
        """
        处理登录逻辑。此版本通过检查登录后页面是否包含"Mypage"链接
        来正确地验证登录是否成功。
        """
        login_url = "https://www.freem.ne.jp/account/login"
        self.logger.info(f"正在尝试登录账户: {self.email}")

        try:
            # 1. 准备POST数据
            payload = {
                'data[User][email_pc]': self.email,
                'data[User][password]': self.password,
                'ref': 'https://www.freem.ne.jp/',
                'data[User][remember_me]': '1'
            }
            self.logger.info("步骤1/2: 准备提交登录表单...")
            
            # 2. 初始化会话
            self.logger.info("正在初始化会话...")
            self.session.get(self.base_url, timeout=20) 

            # 3. 准备带有Referer的请求头
            post_headers = {
                'Referer': login_url
            }
            
            # 4. 发送POST请求进行登录
            self.logger.info("步骤2/2: 发送登录请求...")
            post_response = self.session.post(login_url, data=payload, headers=post_headers, timeout=20)
            post_response.raise_for_status()

            # 5. 【核心修正】验证是否登录成功
            # 成功的登录会重定向到首页，检查首页是否包含"Mypage"链接是最可靠的方法。
            if "/mypage" in post_response.text and "Mypage" in post_response.text:
                self.logger.info("登录成功！现在会话已保持登录状态。")
                return True
            else:
                self.logger.error("登录失败！服务器返回的页面未包含成功标识，请检查账户或密码。")
                with open(os.path.join(self.status_dir, "login_fail_response.html"), "w", encoding="utf-8") as f:
                    f.write(post_response.text)
                self.logger.error("失败的响应页面已保存到 login_fail_response.html")
                return False

        except requests.exceptions.RequestException as e:
            self.logger.error(f"登录过程中发生网络错误: {e}")
            return False

    # ---------------------------------------------------------
    # Rclone 安全上传功能 (无需修改)
    # ---------------------------------------------------------
    def safe_upload_and_delete(self, filepath):
        """【全新重构】使用 Copy-Verify-Delete 策略，并实时显示上传进度"""
        if not os.path.exists(filepath):
            self.logger.error(f"文件不存在，无法上传: {filepath}")
            return False

        filename = os.path.basename(filepath)
        local_size = os.path.getsize(filepath)
        remote_path = f"{self.rclone_remote}/{filename}"

        # 1. 上传 (Copy) 并实时打印进度
        self.logger.info(f"步骤1/3 [上传]: 开始复制 {filename} 到云端...")
        
        copy_cmd = ["rclone", "copy", filepath, self.rclone_remote, "--progress", "--log-level=INFO"]
        
        try:
            # 使用 Popen 实时获取输出
            process = subprocess.Popen(
                copy_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # 将标准错误合并到标准输出
                text=True,
                encoding='utf-8', # 强制使用UTF-8解码
                errors='replace'  # 如果仍有编码错误，则替换为'?'
            )

            # 实时读取并打印Rclone的输出
            print("-" * 20 + " Rclone Upload Progress " + "-" * 20)
            for line in iter(process.stdout.readline, ''):
                # \r 用于将光标移回行首，实现单行刷新进度条的效果
                print(f"\r{line.strip()}", end="")
            process.stdout.close()
            return_code = process.wait()
            print("\n" + "-" * 62) # 进度条结束后换行

            if return_code != 0:
                self.logger.error(f"上传失败! Rclone 返回错误码: {return_code}")
                return False
                
            self.logger.info("上传命令执行完毕，开始验证...")

        except FileNotFoundError:
            self.logger.error("Rclone命令未找到！请确保Rclone已安装并在系统PATH中。")
            return False
        except Exception as e:
            self.logger.error(f"执行Rclone上传时发生未知错误: {e}")
            return False

        # 2. 验证 (Verify)
        self.logger.info(f"步骤2/3 [验证]: 检查云端文件大小...")
        size_cmd = ["rclone", "size", remote_path, "--json"]
        try:
            result = subprocess.run(
                size_cmd, 
                check=True, 
                capture_output=True, 
                text=True,
                encoding='utf-8' # 同样强制UTF-8
            )
            remote_info = json.loads(result.stdout)
            remote_size = remote_info.get("total_size", -1)

            self.logger.info(f"本地大小: {local_size}字节, 云端大小: {remote_size}字节")
            if local_size == remote_size and local_size > 0:
                self.logger.info("验证成功: 文件大小一致。")
                
                # 3. 删除 (Delete)
                self.logger.info(f"步骤3/3 [清理]: 删除本地文件 {filename}...")
                try:
                    os.remove(filepath)
                    self.logger.info("本地文件已成功删除。")
                    return True
                except OSError as e:
                    self.logger.error(f"删除本地文件失败! 错误: {e}")
                    return False
            else:
                self.logger.error("验证失败: 云端与本地文件大小不匹配或大小为0! 本地文件我也给你删了。")
                try:
                    os.remove(filepath)
                    self.logger.info("本地文件已成功删除。")
                    return True
                except OSError as e:
                    self.logger.error(f"删除本地文件失败! 错误: {e}")
                    return False
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"验证云端文件时出错! 错误: {e}")
            return False
            
    # ---------------------------------------------------------
    # 其他方法 (无需修改)
    # ---------------------------------------------------------
    def load_completed_games(self):
        try:
            if os.path.exists(self.completed_log_file):
                with open(self.completed_log_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            self.logger.warning("无法读取完成记录，将创建新记录。")
        return set()

    def log_game_as_completed(self, game_id, completed_set):
        completed_set.add(game_id)
        with open(self.completed_log_file, 'w', encoding='utf-8') as f:
            json.dump(list(completed_set), f, indent=2)
        self.logger.info(f"游戏ID {game_id} 已标记为完成。")

    def get_game_list(self, start_page=1, end_page=253):
        if not self.force_rescan and os.path.exists(self.game_list_cache_file):
            self.logger.info("发现游戏列表缓存，正在从本地加载...")
            with open(self.game_list_cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        self.logger.info("未找到缓存或强制刷新，正在从网站扫描所有页面...")
        all_games = []
        for page in tqdm(range(start_page, end_page + 1), desc="扫描页面", unit="页"):
            page_url = f"{self.base_url}/win/category/4/" if page == 1 else f"{self.base_url}/win/category/4/page-{page}"
            all_games.extend(self.extract_game_links(page_url))
        self.logger.info(f"扫描完成，共发现 {len(all_games)} 个游戏。正在保存到缓存文件...")
        with open(self.game_list_cache_file, 'w', encoding='utf-8') as f:
            json.dump(all_games, f, indent=2)
        return all_games

    def process_all_games(self):
        self.logger.info("--- 自动化流程启动 ---")
        completed_games = self.load_completed_games()
        all_games = self.get_game_list()
        total_games = len(all_games)
        pending_games = [g for g in all_games if g['id'] not in completed_games]
        self.logger.info(f"总游戏数: {total_games}, 已完成: {len(completed_games)}, 待处理: {len(pending_games)}")
        self.logger.info("="*60)
        if not pending_games:
            self.logger.info("所有游戏均已处理完毕，无需操作。")
            return
        for i, game_info in enumerate(pending_games, 1):
            game_id = game_info['id']
            self.logger.info(f"\n>>> [{i}/{len(pending_games)}] 处理新游戏: {game_info['title']} (ID: {game_id})")
            download_page = self.get_download_page_url(game_info['url'])
            if not download_page: continue
            final_url, orig_name, _ = self.get_final_download_url(download_page)
            if not final_url: continue
            filename = self.generate_better_filename(game_info, orig_name)
            filepath = os.path.join(self.download_dir, filename)
            if self.download_file(final_url, filepath):
                if self.safe_upload_and_delete(filepath):
                    self.log_game_as_completed(game_id, completed_games)
                else:
                    self.logger.warning(f"上传/验证失败，文件保留在本地: {filename}")
            else:
                self.logger.error(f"下载失败，跳过: {filename}")
            time.sleep(1)
        self.logger.info("="*60)
        self.logger.info("本轮所有待处理任务已完成！")

    def download_file(self, url, filepath):
        local_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        headers = {'Range': f'bytes={local_size}-'} if local_size > 0 else {}
        try:
            # 【重要】确保下载时使用保持登录状态的 session
            response = self.session.get(url, stream=True, headers=headers, timeout=30)
            if response.status_code in [200, 206]:
                mode = 'wb' if response.status_code == 200 else 'ab'
                if mode == 'wb': local_size = 0
                total_size_str = response.headers.get('Content-Length') if mode == 'wb' else response.headers.get('Content-Range', '0/0').split('/')[-1]
                total_size = int(total_size_str) if total_size_str else 0
                if total_size > 0 and local_size >= total_size:
                    self.logger.info("文件已完整，跳过下载。")
                    return True
                with tqdm(total=total_size, initial=local_size, unit='B', unit_scale=True, desc=os.path.basename(filepath)[:30]) as pbar:
                    with open(filepath, mode) as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk); pbar.update(len(chunk))
                return True
            else:
                self.logger.error(f"服务器返回错误代码: {response.status_code}")
                # 针对登录资源，403/401通常意味着权限问题
                if response.status_code in [401, 403]:
                    self.logger.error("这可能是由于登录会话失效导致的权限问题。")
                return False
        except Exception as e:
            self.logger.error(f"下载异常: {e}")
            return False

    def get_page(self, url):
        try:
            # 【重要】确保所有页面请求都使用同一个 session
            r = self.session.get(url, timeout=20); r.raise_for_status()
            return BeautifulSoup(r.text, 'html.parser')
        except Exception as e:
            self.logger.error(f"页面请求失败: {url} - {e}"); return None

    def extract_game_links(self, page_url):
        soup = self.get_page(page_url)
        if not soup: return []
        links = []
        for item in soup.select('section.new-free-game li.col'):
            try:
                a_tag = item.select_one('a[href*="/win/game/"]')
                if a_tag:
                    gid = re.search(r'/(\d+)$', a_tag['href']).group(1)
                    title = item.select_one('h3').get_text(strip=True)
                    dev = item.select_one('h4 a').get_text(strip=True) if item.select_one('h4 a') else "Unknown"
                    links.append({'id': gid, 'url': urljoin(self.base_url, a_tag['href']), 'title': title, 'developer': dev})
            except Exception: continue
        return links

    # 【已更新】get_download_page_url 和 get_final_download_url 无需再改动，
    # 它们的逻辑现在可以处理登录后的页面了。
    def get_download_page_url(self, game_url):
        soup = self.get_page(game_url)
        if soup:
            btn = soup.select_one('.game-dl-wrapper .game-dl-win a')
            if btn and btn.get('href') and btn['href'] != '#':
              return urljoin(self.base_url, btn['href'])
            else:
                all_possible_links = soup.select('.game-dl-wrapper .game-dl-mac a')
                for link in all_possible_links:
                    href = link.get('href', '')
                    if '/win/' in href:
                        # self.logger.info("启用第二种策略") # 日志可以简化
                        return urljoin(self.base_url, href)  
        return None

    def get_final_download_url(self, dl_page_url):
        soup = self.get_page(dl_page_url)
        if soup:
            link = soup.select_one('#dlLink')
            if link:
                url = urljoin(self.base_url, link['href'])
                name_tag = soup.select_one('.dl-file-name')
                name = name_tag.get_text(strip=True).replace('档案名', '').strip() if name_tag else None
                size_tag = soup.select_one('.dl-file-size')
                size = size_tag.get_text(strip=True).replace('档案容量', '').strip() if size_tag else "Unknown"
                return url, name, size
            else:
                # 增加一个失败日志，帮助调试
                self.logger.error(f"在页面 {dl_page_url} 上未能找到 #dlLink 元素。")
        return None, None, None

    def generate_better_filename(self, info, orig_name):
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", info['title']).strip()
        ext = os.path.splitext(orig_name)[1] if orig_name and '.' in orig_name else '.zip'
        fname = f"{info['id']}_{safe_title}{ext}"
        return fname[:150]

def main():
    force_rescan_flag = '--rescan' in sys.argv
    try:
        app = FreemGameDownloader(force_rescan=force_rescan_flag)
        app.process_all_games()
    except KeyboardInterrupt:
        print("\n[用户中断] 程序已停止。")
    except Exception as e:
        print(f"\n[严重错误] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
