import requests

# 替换为你的 GitHub token
token = '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'
# Gist 文件的内容
file_content = '''# Hello Gist
This is a sample file content.'''

# Gist 数据
data = {
    'description': 'Sample Gist',
    'public': True,  # 设置为 True 以公开 Gist，设置为 False 以私有
    'files': {
        'sample_file.txt': {
            'content': file_content
        }
    }
}

# 请求头
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# 创建 Gist
response = requests.post('https://gist.github.com/0x10240/4b1edb15f7aeb64c29a45674fc3e4e9d', json=data, headers=headers)

# 检查响应
if response.status_code == 201:
    print('Gist created successfully!')
    print('Gist URL:', response.json()['html_url'])
else:
    print('Failed to create Gist:', response.text)
