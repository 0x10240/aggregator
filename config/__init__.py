from dotenv import load_dotenv
import os

# 获取当前文件的路径
config_dir = os.path.dirname(os.path.abspath(__file__))

# 加载 config 文件夹下的 .env 文件
load_dotenv(os.path.join(config_dir, '.env'))

# 从环境变量中读取配置
redis_conn = os.getenv('REDIS_CONN')
github_token = os.getenv('GITHUB_TOKEN')
clash_yaml_gist_id = os.getenv('CLASH_YAML_GIST_ID')
proxy_pool_start_port = int(os.getenv('PROXY_POOL_START_PORT', 42001))
