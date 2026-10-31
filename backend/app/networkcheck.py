"""Opt-in, credential-free connectivity probe using the real outbound wrapper.

docker compose exec money-web python -m app.networkcheck
Does not read saved settings or send notifications; reports no URLs/credentials.
"""
import asyncio
import json
from .security import proxy_summary, request, safe_error


async def diagnose():
    results = []
    # Fixed public endpoint only; never use saved AI/Webhook credentials.
    for scheme in ('http', 'https'):
        url = scheme+'://www.example.com/'
        item = {'protocol': scheme}
        try:
            item.update(proxy_summary(url))
            if item.get('proxy_is_loopback'):
                item['hint'] = '容器环回地址仅指自身；NAS 宿主机代理请使用宿主机 IP 或 host.docker.internal'
            # HTTP is route inspection only: external requests require HTTPS by
            # default, and no diagnostic should loosen that policy.
            if scheme == 'https':
                response = await asyncio.wait_for(request('GET', url, timeout=10, raise_status=False), timeout=15)
                item['status'] = response.status_code
                item['connected'] = response.status_code == 200
        except Exception as exc:
            item.update(connected=False, error=safe_error(exc))
        results.append(item)
    return {'routes': results, 'probe': '固定公共测试站点，不读取 AI/Webhook 设置、不发送推送'}


def main():
    result = asyncio.run(diagnose())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(item.get('connected', True) for item in result['routes']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
