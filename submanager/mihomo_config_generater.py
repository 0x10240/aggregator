import yaml

def generate_yaml_file(input_yaml: str, start_port: int, output_file: str):
    try:
        # 解析输入的YAML
        yaml_data = yaml.safe_load(input_yaml)
        num_proxies = len(yaml_data['proxies'])

        # 构造新的YAML数据
        new_yaml = {
            'allow-lan': True,
            'dns': {
                'enable': True,
                'enhanced-mode': 'fake-ip',
                'fake-ip-range': '198.18.0.1/16',
                'default-nameserver': ['114.114.114.114'],
                'nameserver': ['https://doh.pub/dns-query']
            },
            'listeners': [],
            'proxies': yaml_data['proxies']
        }

        # 创建监听器配置
        new_yaml['listeners'] = [
            {
                'name': f"mixed{i}",
                'type': 'mixed',
                'port': start_port + i,
                'proxy': yaml_data['proxies'][i]['name']
            } for i in range(num_proxies)
        ]

        # 将新的YAML数据写入文件
        with open(output_file, 'w', encoding='utf-8') as yaml_file:
            yaml.dump(new_yaml, yaml_file, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"YAML 文件已生成，保存为 {output_file}，起始端口: {start_port}, 结束端口: {start_port + num_proxies - 1}")

    except Exception as e:
        print(f"处理YAML时发生错误: {e}")

# 调用示例
input_yaml = '''
proxies:
'''

generate_yaml_file(input_yaml, 30001, './config.yaml')
