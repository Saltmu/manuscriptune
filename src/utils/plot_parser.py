import re


def parse_plot(file_path):
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    chapters = []
    current_chapter = None
    current_episode = None

    chapter_pattern = re.compile(r"^(第[一二三四五六七八九十0-9]+章)：(.*)$")
    episode_pattern = re.compile(r"^(第[一二三四五六七八九十0-9]+話)：(.*)$")
    interlude_pattern = re.compile(r"^(幕間[一二三四五六七八九十IVX]+)：(.*)$")

    for line in lines:
        line = line.strip().replace("\u200b", "").replace("\ufeff", "")
        if not line:
            if current_episode:
                current_episode["content"].append("")
            continue

        chapter_match = chapter_pattern.match(line)
        if chapter_match:
            title = chapter_match.group(1)
            name = chapter_match.group(2).strip()
            # If chapter already exists (sometimes there are duplicate titles with extra info),
            # just update the current_chapter to point to it.
            existing_chapter = next((c for c in chapters if c["title"] == title), None)
            if existing_chapter:
                current_chapter = existing_chapter
                # If the new name has more info, update it
                if len(name) > len(current_chapter["name"]):
                    current_chapter["name"] = name
            else:
                current_chapter = {"title": title, "name": name, "episodes": []}
                chapters.append(current_chapter)
            current_episode = None
            continue

        episode_match = episode_pattern.match(line)
        if episode_match:
            current_episode = {
                "title": episode_match.group(1),
                "name": episode_match.group(2).strip(),
                "content": [],
            }
            if current_chapter:
                current_chapter["episodes"].append(current_episode)
            continue

        interlude_match = interlude_pattern.match(line)
        if interlude_match:
            current_episode = {
                "title": interlude_match.group(1),
                "name": interlude_match.group(2).strip(),
                "content": [],
            }
            if current_chapter:
                current_chapter["episodes"].append(current_episode)
            continue

        if current_episode:
            current_episode["content"].append(line)

    return chapters


def list_chapters(chapters):
    for i, chapter in enumerate(chapters):
        print(f"{i+1}. {chapter["title"]}: {chapter["name"]}")
        for j, ep in enumerate(chapter["episodes"]):
            print(f"   - {ep["title"]}: {ep["name"]}")


def get_chapter_episodes(chapters, chapter_title):
    for chapter in chapters:
        if chapter["title"] == chapter_title:
            return chapter["episodes"]
    return None
