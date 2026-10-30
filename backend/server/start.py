"""Exec-form Docker entry point: signals reach uvicorn and its task worker."""

import os
import uvicorn


def main():
    workers = int(os.getenv('TDR_API_WORKERS', os.getenv('WORKERS', '1')))
    if workers != 1:
        raise SystemExit('持久任务服务首版要求单个 API 进程；请设置 TDR_API_WORKERS=1')
    uvicorn.run('main:app', host=os.getenv('HOST','0.0.0.0'),
                port=int(os.getenv('PORT','8000')), workers=1)


if __name__ == '__main__':
    main()
