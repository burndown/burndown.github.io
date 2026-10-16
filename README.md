# burndown.github.io

个人博客，地址是 https://burndown.github.io/ 。用 [Hugo](https://gohugo.io/) 和 [PaperMod](https://github.com/adityatelange/hugo-PaperMod) 主题构建，推送到 `main` 后由 GitHub Actions 自动发布到 GitHub Pages。

文章的原稿不在这个仓库里，而是写在我的 Obsidian 笔记库中。`tools/sync.py` 负责把标记为发布的文章同步到 `content/posts/`，同时做三件事：

- **图片**：把 Obsidian 的 `![[图片]]` 换成普通 Markdown 图片，缩到长边 1600 像素，并去掉 EXIF 信息。
- **中英文空格**：用 [pangu](https://pypi.org/project/pangu/) 在中文和英文、数字之间加空格，跳过代码、链接地址和 Markdown 标记。
- **分类**：`writing/esp32/` 里的文章归入"ESP32"，`writing/read/` 里的归入"导读"。

"导读"分类里是我对别人文章的中文摘要，版权归原作者，全文请看文中的原文链接。

## 发布

```sh
python3 -m venv .venv && .venv/bin/pip install pillow pangu   # 第一次
.venv/bin/python tools/sync.py
hugo server            # 本地预览
git add -A && git commit -m "..." && git push
```

克隆时带上主题子模块：`git clone --recurse-submodules`。

`hexo-2025-archive` 分支保存着 2025 年的旧 Hexo 站点。
