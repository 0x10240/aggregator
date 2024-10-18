import json
import base64
import urllib.parse


class ObjectUtil:
    @staticmethod
    def isEmpty(value):
        return value is None or value == ''

    @staticmethod
    def isArrEmpty(value):
        return not value or len(value) == 0


class Protocols:
    VMESS = 'vmess'
    VLESS = 'vless'
    SS = 'shadowsocks'
    TROJAN = 'trojan'
    # Add other protocols if necessary


def safeBase64(input_str):
    """Encode a string using URL-safe Base64 without padding."""
    encoded = base64.urlsafe_b64encode(input_str.encode('utf-8')).decode('utf-8')
    return encoded.rstrip('=')


class ConfigGenerator:
    def __init__(self, config):
        # Parse the configuration dictionaries from JSON strings
        self.config = config
        self.protocol = config.get('protocol')
        self.port = config.get('port')
        self.settings = json.loads(config.get('settings', '{}'))
        self.streamSettings = json.loads(config.get('streamSettings', '{}'))
        self.sniffing = json.loads(config.get('sniffing', '{}'))

    def getHeader(self, obj, header_name):
        """Retrieve a header value from an object."""
        headers = obj.get('headers', [])
        for header in headers:
            if header.get('name', '').lower() == header_name.lower():
                return header.get('value')
        return None

    def genVmessLink(self, address='', port=None, forceTls=None, remark=''):
        if self.protocol != Protocols.VMESS:
            return ''

        clientId = self.settings["clients"][0]["id"],
        security = self.streamSettings.get('security') if forceTls == 'same' else forceTls
        obj = {
            'v': '2',
            'ps': remark,
            'add': address,
            'port': port,
            'id': clientId,
            'net': self.streamSettings.get('network'),
            'type': 'none',
            'tls': security,
        }
        network = self.streamSettings.get('network')
        match network:
            case 'tcp':
                tcp = self.streamSettings.get('tcpSettings', {})
                obj['type'] = tcp.get('type')
                if tcp.get('type') == 'http':
                    request = tcp.get('request', {})
                    obj['path'] = ','.join(request.get('path', []))
                    host = self.getHeader(request, 'host')
                    if host:
                        obj['host'] = host
            case 'kcp':
                kcp = self.streamSettings.get('kcpSettings', {})
                obj['type'] = kcp.get('type')
                obj['path'] = kcp.get('seed')
            case 'ws':
                ws = self.streamSettings.get('wsSettings', {})
                obj['path'] = ws.get('path')
                host = ws.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    obj['host'] = host
            case 'http':
                http = self.streamSettings.get('httpSettings', {})
                obj['net'] = 'h2'
                obj['path'] = http.get('path')
                obj['host'] = ','.join(http.get('host', []))
            case 'quic':
                quic = self.streamSettings.get('quicSettings', {})
                obj['type'] = quic.get('type')
                obj['host'] = quic.get('security')
                obj['path'] = quic.get('key')
            case 'grpc':
                grpc = self.streamSettings.get('grpcSettings', {})
                obj['path'] = grpc.get('serviceName')
                obj['authority'] = grpc.get('authority')
                if grpc.get('multiMode'):
                    obj['type'] = 'multi'
            case 'httpupgrade':
                httpupgrade = self.streamSettings.get('httpSettings', {})
                obj['path'] = httpupgrade.get('path')
                host = httpupgrade.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    obj['host'] = host
            case 'splithttp':
                splithttp = self.streamSettings.get('splitHttpSettings', {})
                obj['path'] = splithttp.get('path')
                host = splithttp.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    obj['host'] = host

        if security == 'tls':
            tlsSettings = self.streamSettings.get('tlsSettings', {})
            if not ObjectUtil.isEmpty(tlsSettings.get('serverName')):
                obj['sni'] = tlsSettings.get('serverName')
            if not ObjectUtil.isEmpty(tlsSettings.get('fingerprint')):
                obj['fp'] = tlsSettings.get('fingerprint')
            alpn = tlsSettings.get('alpn', [])
            if alpn:
                obj['alpn'] = ','.join(alpn)
            if tlsSettings.get('allowInsecure'):
                obj['allowInsecure'] = tlsSettings.get('allowInsecure')

        json_string = json.dumps(obj, indent=2)
        encoded_string = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')
        return 'vmess://' + encoded_string

    def genVLESSLink(self, address='', port=None, forceTls=None, remark=''):
        type_ = self.streamSettings.get('network')
        security = self.streamSettings.get('security') if forceTls == 'same' else forceTls
        params = {}
        params["type"] = type_

        match type_:
            case "tcp":
                tcp = self.streamSettings.get('tcpSettings', {})
                if tcp.get('type') == 'http':
                    request = tcp.get('request', {})
                    params["path"] = ','.join(request.get('path', []))
                    host = self.getHeader(request, 'host')
                    if host:
                        params["host"] = host
                    params["headerType"] = 'http'
            case "kcp":
                kcp = self.streamSettings.get('kcpSettings', {})
                params["headerType"] = kcp.get('type')
                params["seed"] = kcp.get('seed')
            case "ws":
                ws = self.streamSettings.get('wsSettings', {})
                params["path"] = ws.get('path')
                host = ws.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host
            case "http":
                http = self.streamSettings.get('httpSettings', {})
                params["path"] = http.get('path')
                params["host"] = ','.join(http.get('host', []))
            case "quic":
                quic = self.streamSettings.get('quicSettings', {})
                params["quicSecurity"] = quic.get('security')
                params["key"] = quic.get('key')
                params["headerType"] = quic.get('type')
            case "grpc":
                grpc = self.streamSettings.get('grpcSettings', {})
                params["serviceName"] = grpc.get('serviceName')
                params["authority"] = grpc.get('authority')
                if grpc.get('multiMode'):
                    params["mode"] = "multi"
            case "httpupgrade":
                httpupgrade = self.streamSettings.get('httpSettings', {})
                params["path"] = httpupgrade.get('path')
                host = httpupgrade.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host
            case "splithttp":
                splithttp = self.streamSettings.get('splitHttpSettings', {})
                params["path"] = splithttp.get('path')
                host = splithttp.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host


        flow = self.settings["clients"][0].get("flow", "")

        if security == 'tls':
            params["security"] = "tls"
            tlsSettings = self.streamSettings.get('tlsSettings', {})
            params["fp"] = tlsSettings.get('fingerprint')
            params["alpn"] = ','.join(tlsSettings.get('alpn', []))
            if tlsSettings.get('allowInsecure'):
                params["allowInsecure"] = "1"
            if not ObjectUtil.isEmpty(tlsSettings.get('serverName')):
                params["sni"] = tlsSettings.get('serverName')
            if type_ == "tcp" and not ObjectUtil.isEmpty(flow):
                params["flow"] = flow
        elif security == 'reality':
            params["security"] = "reality"
            realitySettings = self.streamSettings.get('realitySettings', {})
            params["pbk"] = realitySettings.get('publicKey')
            params["fp"] = realitySettings.get('fingerprint')
            serverNames = realitySettings.get('serverNames', '')
            if not ObjectUtil.isArrEmpty(serverNames):
                params["sni"] = serverNames.split(",")[0]
            shortIds = realitySettings.get('shortIds', '')
            if shortIds:
                params["sid"] = shortIds.split(",")[0]
            if not ObjectUtil.isEmpty(realitySettings.get('spiderX')):
                params["spx"] = realitySettings.get('spiderX')
            if type_ == 'tcp' and not ObjectUtil.isEmpty(flow):
                params["flow"] = flow
        else:
            params["security"] = "none"

        client_id = self.settings["clients"][0]["id"]
        link = f'vless://{client_id}@{address}:{port}'
        url_parts = list(urllib.parse.urlparse(link))
        query = dict(urllib.parse.parse_qsl(url_parts[4]))
        query.update(params)
        url_parts[4] = urllib.parse.urlencode(query, doseq=True)
        url_parts[5] = urllib.parse.quote(remark)
        return urllib.parse.urlunparse(url_parts)

    def genSSLink(self, address='', port=None, forceTls=None, remark='', clientPassword=None):
        settings = self.settings
        type_ = self.streamSettings.get('network')
        security = self.streamSettings.get('security') if forceTls == 'same' else forceTls
        params = {}
        params["type"] = type_

        match type_:
            case "tcp":
                tcp = self.streamSettings.get('tcpSettings', {})
                if tcp.get('type') == 'http':
                    request = tcp.get('request', {})
                    params["path"] = ','.join(request.get('path', []))
                    host = self.getHeader(request, 'host')
                    if host:
                        params["host"] = host
                    params["headerType"] = 'http'
            case "kcp":
                kcp = self.streamSettings.get('kcpSettings', {})
                params["headerType"] = kcp.get('type')
                params["seed"] = kcp.get('seed')
            case "ws":
                ws = self.streamSettings.get('wsSettings', {})
                params["path"] = ws.get('path')
                host = ws.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host
            case "http":
                http = self.streamSettings.get('httpSettings', {})
                params["path"] = http.get('path')
                params["host"] = ','.join(http.get('host', []))
            case "quic":
                quic = self.streamSettings.get('quicSettings', {})
                params["quicSecurity"] = quic.get('security')
                params["key"] = quic.get('key')
                params["headerType"] = quic.get('type')
            case "grpc":
                grpc = self.streamSettings.get('grpcSettings', {})
                params["serviceName"] = grpc.get('serviceName')
                params["authority"] = grpc.get('authority')
                if grpc.get('multiMode'):
                    params["mode"] = "multi"
            case "httpupgrade":
                httpupgrade = self.streamSettings.get('httpSettings', {})
                params["path"] = httpupgrade.get('path')
                host = httpupgrade.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host
            case "splithttp":
                splithttp = self.streamSettings.get('splitHttpSettings', {})
                params["path"] = splithttp.get('path')
                host = splithttp.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host

        if security == 'tls':
            params["security"] = "tls"
            tlsSettings = self.streamSettings.get('tlsSettings', {})
            params["fp"] = tlsSettings.get('fingerprint')
            params["alpn"] = ','.join(tlsSettings.get('alpn', []))
            if tlsSettings.get('allowInsecure'):
                params["allowInsecure"] = "1"
            if not ObjectUtil.isEmpty(tlsSettings.get('serverName')):
                params["sni"] = tlsSettings.get('serverName'

                                                )
        password = []
        if self.isSS2022:
            password.append(settings.get('password'))
        if self.isSSMultiUser:
            password.append(clientPassword)

        credential = f"{settings.get('method')}:{':'.join(password)}"
        encoded_credential = safeBase64(credential)
        link = f'ss://{encoded_credential}@{address}:{port}'
        url_parts = list(urllib.parse.urlparse(link))
        query = dict(urllib.parse.parse_qsl(url_parts[4]))
        query.update(params)
        url_parts[4] = urllib.parse.urlencode(query, doseq=True)
        url_parts[5] = urllib.parse.quote(remark)
        return urllib.parse.urlunparse(url_parts)

    def genTrojanLink(self, address='', port=None, forceTls=None, remark='', clientPassword=None):
        security = self.streamSettings.get('security') if forceTls == 'same' else forceTls
        type_ = self.streamSettings.get('network')
        params = {}
        params["type"] = type_

        match type_:
            case "tcp":
                tcp = self.streamSettings.get('tcpSettings', {})
                if tcp.get('type') == 'http':
                    request = tcp.get('request', {})
                    params["path"] = ','.join(request.get('path', []))
                    host = self.getHeader(request, 'host')
                    if host:
                        params["host"] = host
                    params["headerType"] = 'http'
            case "kcp":
                kcp = self.streamSettings.get('kcpSettings', {})
                params["headerType"] = kcp.get('type')
                params["seed"] = kcp.get('seed')
            case "ws":
                ws = self.streamSettings.get('wsSettings', {})
                params["path"] = ws.get('path')
                host = ws.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host
            case "http":
                http = self.streamSettings.get('httpSettings', {})
                params["path"] = http.get('path')
                params["host"] = ','.join(http.get('host', []))
            case "quic":
                quic = self.streamSettings.get('quicSettings', {})
                params["quicSecurity"] = quic.get('security')
                params["key"] = quic.get('key')
                params["headerType"] = quic.get('type')
            case "grpc":
                grpc = self.streamSettings.get('grpcSettings', {})
                params["serviceName"] = grpc.get('serviceName')
                params["authority"] = grpc.get('authority')
                if grpc.get('multiMode'):
                    params["mode"] = "multi"
            case "httpupgrade":
                httpupgrade = self.streamSettings.get('httpSettings', {})
                params["path"] = httpupgrade.get('path')
                host = httpupgrade.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host
            case "splithttp":
                splithttp = self.streamSettings.get('splitHttpSettings', {})
                params["path"] = splithttp.get('path')
                host = splithttp.get('headers', {}).get('Host')
                if host and len(host) > 0:
                    params["host"] = host

        if security == 'tls':
            params["security"] = "tls"
            tlsSettings = self.streamSettings.get('tlsSettings', {})
            params["fp"] = tlsSettings.get('fingerprint')
            params["alpn"] = ','.join(tlsSettings.get('alpn', []))
            if tlsSettings.get('allowInsecure'):
                params["allowInsecure"] = "1"
            if not ObjectUtil.isEmpty(tlsSettings.get('serverName')):
                params["sni"] = tlsSettings.get('serverName')
        elif security == 'reality':
            params["security"] = "reality"
            realitySettings = self.streamSettings.get('realitySettings', {})
            params["pbk"] = realitySettings.get('publicKey')
            params["fp"] = realitySettings.get('fingerprint')
            serverNames = realitySettings.get('serverNames', '')
            if not ObjectUtil.isArrEmpty(serverNames):
                params["sni"] = serverNames.split(",")[0]
            shortIds = realitySettings.get('shortIds', '')
            if shortIds:
                params["sid"] = shortIds.split(",")[0]
            if not ObjectUtil.isEmpty(realitySettings.get('spiderX')):
                params["spx"] = realitySettings.get('spiderX')
        else:
            params["security"] = "none"

        link = f'trojan://{clientPassword}@{address}:{port}'
        url_parts = list(urllib.parse.urlparse(link))
        query = dict(urllib.parse.parse_qsl(url_parts[4]))
        query.update(params)
        url_parts[4] = urllib.parse.urlencode(query, doseq=True)
        url_parts[5] = urllib.parse.quote(remark)
        return urllib.parse.urlunparse(url_parts)


if __name__ == '__main__':
    # 您的配置字典
    config = {}

    # 初始化 ConfigGenerator
    generator = ConfigGenerator(config)

    # 生成 VLESS 链接
    vless_link = generator.genVLESSLink(
        address='example.com',
        port=generator.port,
        forceTls='same',
        remark=config["remark"],
    )

    print(vless_link)
