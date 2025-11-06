import requests
from bs4 import BeautifulSoup
import os
import time
import re
from urllib.parse import urljoin
import logging
from tqdm import tqdm
import sys

class FreemGameDownloader:
    def __init__(self, download_dir=None):
        self.base_url = "https://www.freem.ne.jp"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 交互式选择下载目录
        if download_dir is None:
            self.download_dir = self.choose_download_directory()
        else:
            self.download_dir = download_dir
        
        # 创建下载目录
        os.makedirs(self.download_dir, exist_ok=True)
        
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(self.download_dir, 'download.log'), encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def choose_download_directory(self):
        """交互式选择下载目录"""
        print("\n" + "="*50)
        print("Freem游戏下载器")
        print("="*50)
        
        # 显示当前目录
        current_dir = os.getcwd()
        print(f"当前目录: {current_dir}")
        
        while True:
            print("\n请选择下载目录:")
            print("1. 使用当前目录")
            print("2. 使用当前目录下的 'downloads' 文件夹")
            print("3. 输入自定义路径")
            
            choice = input("请选择 (1/2/3): ").strip()
            
            if choice == "1":
                download_dir = current_dir
                break
            elif choice == "2":
                download_dir = os.path.join(current_dir, "downloads")
                break
            elif choice == "3":
                custom_path = input("请输入完整路径: ").strip()
                if custom_path:
                    download_dir = custom_path
                    # 展开用户目录（支持 ~）
                    download_dir = os.path.expanduser(download_dir)
                    break
                else:
                    print("路径不能为空，请重新输入。")
            else:
                print("无效选择，请重新输入。")
        
        # 确认目录
        print(f"\n下载目录设置为: {download_dir}")
        confirm = input("确认使用此目录？(y/n): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            return self.choose_download_directory()
        
        return download_dir

    def get_page(self, url):
        """获取页面内容"""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            self.logger.error(f"获取页面失败 {url}: {e}")
            return None

    def extract_game_links(self, page_url):
        """从列表页提取游戏链接"""
        soup = self.get_page(page_url)
        if not soup:
            return []
        
        game_links = []
        game_section = soup.find('section', class_='new-free-game')
        
        if game_section:
            game_items = game_section.find_all('li', class_='col')
            
            for item in game_items:
                try:
                    link_tag = item.find('a', href=re.compile(r'/win/game/\d+'))
                    if link_tag:
                        game_url = urljoin(self.base_url, link_tag['href'])
                        
                        # 提取游戏信息
                        title_tag = item.find('h3', class_='pc') or item.find('h3')
                        title = title_tag.get_text(strip=True) if title_tag else "未知标题"
                        
                        developer_tag = item.find('h4').find('a') if item.find('h4') else None
                        developer = developer_tag.get_text(strip=True) if developer_tag else "未知开发者"
                        
                        desc_tag = item.find('p')
                        description = desc_tag.get_text(strip=True) if desc_tag else "无描述"
                        
                        # 提取游戏ID
                        game_id = re.search(r'/win/game/(\d+)', link_tag['href'])
                        game_id = game_id.group(1) if game_id else "unknown"
                        
                        game_links.append({
                            'url': game_url,
                            'title': title,
                            'developer': developer,
                            'description': description,
                            'id': game_id
                        })
                except Exception as e:
                    self.logger.error(f"提取游戏信息失败: {e}")
                    continue
        
        self.logger.info(f"从 {page_url} 提取到 {len(game_links)} 个游戏")
        return game_links

    def get_download_page_url(self, game_url):
        """从游戏详情页获取下载页面URL"""
        soup = self.get_page(game_url)
        if not soup:
            return None
        
        try:
            # 查找红色Windows下载按钮
            download_section = soup.find('section', class_='game-dl-wrapper')
            if download_section:
                windows_btn = download_section.find('div', class_='game-dl-win')
                if windows_btn:
                    download_link = windows_btn.find('a')
                    if download_link and download_link.get('href'):
                        return urljoin(self.base_url, download_link['href'])
            
            self.logger.warning(f"在 {game_url} 中未找到下载按钮")
            return None
        except Exception as e:
            self.logger.error(f"获取下载页面URL失败 {game_url}: {e}")
            return None

    def get_final_download_url(self, download_page_url):
        """从下载页面获取最终下载URL和文件信息"""
        soup = self.get_page(download_page_url)
        if not soup:
            return None, None, None
        
        try:
            # 查找最终下载按钮
            download_btn = soup.find('div', class_='btn-dl')
            if download_btn:
                final_link = download_btn.find('a', id='dlLink')
                if final_link and final_link.get('href'):
                    final_url = urljoin(self.base_url, final_link['href'])
                    
                    # 获取文件信息
                    file_name_elem = soup.find('p', class_='dl-file-name')
                    file_size_elem = soup.find('p', class_='dl-file-size')
                    
                    original_filename = None
                    file_size = "未知大小"
                    
                    if file_name_elem:
                        # 提取文件名（跳过"档案名"文本）
                        file_text = file_name_elem.get_text(strip=True)
                        original_filename = re.sub(r'^档案名\s*', '', file_text)
                    
                    if file_size_elem:
                        file_text = file_size_elem.get_text(strip=True)
                        file_size = re.sub(r'^档案容量\s*', '', file_text)
                    
                    return final_url, original_filename, file_size
            
            self.logger.warning(f"在 {download_page_url} 中未找到最终下载链接")
            return None, None, None
        except Exception as e:
            self.logger.error(f"获取最终下载URL失败 {download_page_url}: {e}")
            return None, None, None

    def generate_better_filename(self, game_info, original_filename):
        """生成更好的文件名"""
        title = self.sanitize_filename(game_info['title'])
        developer = self.sanitize_filename(game_info['developer'])
        game_id = game_info['id']
        
        # 如果有原始文件名，提取扩展名
        if original_filename and '.' in original_filename:
            extension = '.' + original_filename.split('.')[-1]
        else:
            extension = '.zip'  # 默认扩展名
        
        # 生成新文件名：ID_标题_开发者.扩展名
        new_filename = f"{game_id}_{title}_{developer}{extension}"
        
        # 限制文件名长度（Windows最大255字符，我们限制在150）
        if len(new_filename) > 150:
            # 缩短标题部分
            max_title_length = 150 - len(f"{game_id}_{developer}{extension}") - 10
            if max_title_length > 10:
                title = title[:max_title_length]
                new_filename = f"{game_id}_{title}_{developer}{extension}"
            else:
                # 如果还是太长，使用更简单的格式
                new_filename = f"{game_id}_{title}{extension}"[:150]
        
        return new_filename

    def download_file_with_progress(self, url, filename, game_info, file_size_text="未知大小"):
        """带进度条下载文件"""
        try:
            filepath = os.path.join(self.download_dir, filename)
            
            # 如果文件已存在，跳过下载
            if os.path.exists(filepath):
                self.logger.info(f"文件已存在，跳过: {filename}")
                return True
            
            self.logger.info(f"开始下载: {filename} ({file_size_text})")
            
            # 发起请求
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            # 获取文件大小（用于进度条）
            total_size = int(response.headers.get('content-length', 0))
            
            # 创建进度条
            progress_bar = tqdm(
                total=total_size,
                unit='B',
                unit_scale=True,
                desc=filename[:40],  # 限制描述长度
                ncols=80
            )
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress_bar.update(len(chunk))
            
            progress_bar.close()
            
            # 验证文件大小
            actual_size = os.path.getsize(filepath)
            if total_size > 0 and actual_size != total_size:
                self.logger.error(f"文件大小不匹配: 期望 {total_size}, 实际 {actual_size}")
                os.remove(filepath)
                return False
            
            self.logger.info(f"下载完成: {filename}")
            
            # 保存游戏信息
            self.save_game_info(filename, game_info, file_size_text)
            
            return True
        except Exception as e:
            self.logger.error(f"下载文件失败 {filename}: {e}")
            # 如果下载失败，删除可能不完整的文件
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)
            return False

    def save_game_info(self, filename, game_info, file_size):
        """保存游戏信息到文本文件"""
        try:
            info_filename = os.path.splitext(filename)[0] + '_info.txt'
            info_filepath = os.path.join(self.download_dir, info_filename)
            
            with open(info_filepath, 'w', encoding='utf-8') as f:
                f.write("="*50 + "\n")
                f.write("游戏信息\n")
                f.write("="*50 + "\n")
                f.write(f"标题: {game_info['title']}\n")
                f.write(f"开发者: {game_info['developer']}\n")
                f.write(f"文件大小: {file_size}\n")
                f.write(f"游戏ID: {game_info['id']}\n")
                f.write(f"下载时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"原始URL: {game_info['url']}\n")
                f.write("\n描述:\n")
                f.write(game_info['description'] + "\n")
            
            self.logger.debug(f"游戏信息已保存: {info_filename}")
        except Exception as e:
            self.logger.error(f"保存游戏信息失败: {e}")

    def sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        # 替换Windows非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 替换其他可能的问题字符
        filename = re.sub(r'[\s]+', ' ', filename)
        filename = filename.strip()
        return filename

    def download_all_games(self, start_page=1, end_page=253, delay=2):
        """下载所有游戏"""
        total_downloaded = 0
        total_failed = 0
        
        print(f"\n开始下载第 {start_page} 到 {end_page} 页的游戏...")
        print(f"下载目录: {self.download_dir}")
        
        for page in range(start_page, end_page + 1):
            self.logger.info(f"正在处理第 {page} 页...")
            print(f"\n处理第 {page}/{end_page} 页...")
            
            if page == 1:
                page_url = f"{self.base_url}/win/category/4/"
            else:
                page_url = f"{self.base_url}/win/category/4/page-{page}"
            
            game_links = self.extract_game_links(page_url)
            
            if not game_links:
                print(f"第 {page} 页没有找到游戏，跳过...")
                continue
            
            page_downloaded = 0
            page_failed = 0
            
            for i, game_info in enumerate(game_links, 1):
                try:
                    print(f"\n[{i}/{len(game_links)}] 处理游戏: {game_info['title']}")
                    
                    # 第一步：获取下载页面URL
                    download_page_url = self.get_download_page_url(game_info['url'])
                    if not download_page_url:
                        print(f"  ❌ 无法找到下载页面")
                        page_failed += 1
                        continue
                    
                    # 第二步：获取最终下载URL和文件信息
                    final_url, original_filename, file_size = self.get_final_download_url(download_page_url)
                    if not final_url:
                        print(f"  ❌ 无法找到下载链接")
                        page_failed += 1
                        continue
                    
                    # 第三步：生成更好的文件名
                    better_filename = self.generate_better_filename(game_info, original_filename)
                    print(f"  📁 文件名: {better_filename}")
                    print(f"  📊 文件大小: {file_size}")
                    
                    # 第四步：下载文件
                    if self.download_file_with_progress(final_url, better_filename, game_info, file_size):
                        print(f"  ✅ 下载成功")
                        page_downloaded += 1
                    else:
                        print(f"  ❌ 下载失败")
                        page_failed += 1
                    
                    # 延迟避免被封
                    if i < len(game_links):  # 最后一个游戏不需要延迟
                        time.sleep(delay)
                    
                except Exception as e:
                    self.logger.error(f"处理游戏失败 {game_info['title']}: {e}")
                    print(f"  ❌ 处理失败: {e}")
                    page_failed += 1
                    continue
            
            total_downloaded += page_downloaded
            total_failed += page_failed
            
            print(f"\n第 {page} 页完成: 成功 {page_downloaded}, 失败 {page_failed}")
        
        print(f"\n" + "="*50)
        print(f"下载总结:")
        print(f"总成功: {total_downloaded}")
        print(f"总失败: {total_failed}")
        print(f"下载目录: {self.download_dir}")
        print("="*50)

    def download_single_game(self, game_url):
        """下载单个游戏"""
        # 提取游戏信息
        soup = self.get_page(game_url)
        if not soup:
            print("无法访问游戏页面")
            return False
        
        try:
            # 提取游戏标题
            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else "未知标题"
            
            # 提取开发者
            developer_elem = soup.find('h3').find('a') if soup.find('h3') else None
            developer = developer_elem.get_text(strip=True) if developer_elem else "未知开发者"
            
            # 提取游戏ID
            game_id = re.search(r'/win/game/(\d+)', game_url)
            game_id = game_id.group(1) if game_id else "unknown"
            
            game_info = {
                'url': game_url,
                'title': title,
                'developer': developer,
                'description': '单个游戏下载',
                'id': game_id
            }
            
            print(f"\n开始下载单个游戏: {title}")
            
            download_page_url = self.get_download_page_url(game_url)
            if download_page_url:
                final_url, original_filename, file_size = self.get_final_download_url(download_page_url)
                if final_url:
                    better_filename = self.generate_better_filename(game_info, original_filename)
                    print(f"文件名: {better_filename}")
                    print(f"文件大小: {file_size}")
                    
                    success = self.download_file_with_progress(final_url, better_filename, game_info, file_size)
                    if success:
                        print("✅ 下载完成!")
                    else:
                        print("❌ 下载失败!")
                    return success
            return False
        except Exception as e:
            self.logger.error(f"下载单个游戏失败: {e}")
            print(f"❌ 下载失败: {e}")
            return False

def main():
    downloader = FreemGameDownloader()
    
    while True:
        print("\n" + "="*50)
        print("Freem游戏下载器 - 主菜单")
        print("="*50)
        print("1. 下载所有游戏 (1-253页)")
        print("2. 下载指定页面范围")
        print("3. 下载单个游戏")
        print("4. 更改下载目录")
        print("5. 退出")
        
        choice = input("\n请输入选择 (1/2/3/4/5): ").strip()
        
        if choice == "1":
            print("\n开始下载所有游戏...")
            downloader.download_all_games(start_page=1, end_page=253)
        
        elif choice == "2":
            try:
                start = int(input("起始页码: "))
                end = int(input("结束页码: "))
                if 1 <= start <= end <= 253:
                    downloader.download_all_games(start_page=start, end_page=end)
                else:
                    print("页码范围无效，应为 1-253")
            except ValueError:
                print("请输入有效的数字")
        
        elif choice == "3":
            url = input("游戏URL: ").strip()
            if url:
                if not url.startswith('http'):
                    url = f"https://www.freem.ne.jp{url}"
                downloader.download_single_game(url)
            else:
                print("URL不能为空")
        
        elif choice == "4":
            new_dir = downloader.choose_download_directory()
            downloader.download_dir = new_dir
            downloader.logger.info(f"下载目录已更改为: {new_dir}")
            print(f"下载目录已更改为: {new_dir}")
        
        elif choice == "5":
            print("谢谢使用，再见！")
            break
        
        else:
            print("无效选择，请重新输入")
        
        input("\n按Enter键继续...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序发生错误: {e}")