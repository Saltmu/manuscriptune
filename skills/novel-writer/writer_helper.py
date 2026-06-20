import re
import argparse
import os
import glob

def resolve_latest_file(pattern, default=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    full_pattern = os.path.join(project_root, pattern)
    files = glob.glob(full_pattern)
    if not files:
        files = glob.glob(pattern)
        if not files:
            return default
    files.sort()
    return files[-1]

def parse_plot(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    chapters = []
    current_chapter = None
    current_episode = None
    
    chapter_pattern = re.compile(r'^(第[一二三四五六七八九十0-9]+章)：(.*)$')
    episode_pattern = re.compile(r'^(第[一二三四五六七八九十0-9]+話)：(.*)$')
    interlude_pattern = re.compile(r'^(幕間[一二三四五六七八九十IVX]+)：(.*)$')

    for line in lines:
        line = line.strip().replace('\u200b', '').replace('\ufeff', '')
        if not line:
            if current_episode:
                current_episode['content'].append('')
            continue

        chapter_match = chapter_pattern.match(line)
        if chapter_match:
            title = chapter_match.group(1)
            name = chapter_match.group(2).strip()
            # If chapter already exists (sometimes there are duplicate titles with extra info),
            # just update the current_chapter to point to it.
            existing_chapter = next((c for c in chapters if c['title'] == title), None)
            if existing_chapter:
                current_chapter = existing_chapter
                # If the new name has more info, update it
                if len(name) > len(current_chapter['name']):
                    current_chapter['name'] = name
            else:
                current_chapter = {
                    'title': title,
                    'name': name,
                    'episodes': []
                }
                chapters.append(current_chapter)
            current_episode = None
            continue

        episode_match = episode_pattern.match(line)
        if episode_match:
            current_episode = {
                'title': episode_match.group(1),
                'name': episode_match.group(2).strip(),
                'content': []
            }
            if current_chapter:
                current_chapter['episodes'].append(current_episode)
            continue
            
        interlude_match = interlude_pattern.match(line)
        if interlude_match:
            current_episode = {
                'title': interlude_match.group(1),
                'name': interlude_match.group(2).strip(),
                'content': []
            }
            if current_chapter:
                current_chapter['episodes'].append(current_episode)
            continue

        if current_episode:
            current_episode['content'].append(line)

    return chapters

def list_chapters(chapters):
    for i, chapter in enumerate(chapters):
        print(f"{i+1}. {chapter['title']}: {chapter['name']}")
        for j, ep in enumerate(chapter['episodes']):
            print(f"   - {ep['title']}: {ep['name']}")

def get_chapter_episodes(chapters, chapter_title):
    for chapter in chapters:
        if chapter['title'] == chapter_title:
            return chapter['episodes']
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse novel plot files.")
    default_plot = resolve_latest_file("data/sources/*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt")
    parser.add_argument("--file", default=default_plot, help="Path to the plot file.")
    parser.add_argument("--list", action="store_true", help="List all chapters and episodes.")
    parser.add_argument("--get-chapter", type=str, help="Get episodes for a specific chapter (e.g., '第1章').")
    
    args = parser.parse_args()
    
    # Adjust path if relative
    plot_file = args.file
    if not os.path.isabs(plot_file):
        # Assuming project root is current working directory
        pass

    if os.path.exists(plot_file):
        plot_data = parse_plot(plot_file)
        
        if args.list:
            list_chapters(plot_data)
        elif args.get_chapter:
            episodes = get_chapter_episodes(plot_data, args.get_chapter)
            if episodes:
                import json
                print(json.dumps(episodes, ensure_ascii=False, indent=2))
            else:
                print(f"Chapter {args.get_chapter} not found.")
    else:
        print(f"File not found: {plot_file}")
