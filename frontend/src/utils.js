import { isRunningProcess, consoleLogMap, consoleStatusMap } from './store.js';

export function parseLineNumber(locationStr) {
    if (!locationStr) return null;
    const match = String(locationStr).match(/(\d+)/);
    return match ? parseInt(match[0], 10) : null;
}

export function showToast(message, duration = 1500) {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => { toast.classList.remove('show'); }, duration);
    }
}

// Simple event stream handler using stores instead of direct DOM manipulation
export function startEventStream(url, consoleKey, onComplete = null) {
    consoleLogMap.update(map => ({ ...map, [consoleKey]: '--- プロセスを開始します ---\n' }));
    consoleStatusMap.update(map => ({ ...map, [consoleKey]: 'RUNNING' }));
    isRunningProcess.set(true);

    const eventSource = new EventSource(url);
    let requestId = null;

    eventSource.onmessage = function(event) {
        // First message contains request_id for cancellation
        if (event.data.includes('[REQUEST_ID]')) {
            requestId = event.data.split('[REQUEST_ID]')[1].trim();
            return;
        }

        if (event.data.includes('[PROCESS_EXITED]')) {
            const code = event.data.split('code=')[1] || '0';
            const logSuffix = `\n--- プロセスが終了しました (終了コード: ${code}) ---\n`;

            consoleLogMap.update(map => ({ ...map, [consoleKey]: map[consoleKey] + logSuffix }));
            consoleStatusMap.update(map => ({ ...map, [consoleKey]: code === '0' ? 'COMPLETED' : 'FAILED' }));

            eventSource.close();
            isRunningProcess.set(false);

            if (onComplete) onComplete(code === '0');
            return;
        }

        if (event.data.includes('[PROCESS_CANCELLED]')) {
            const logSuffix = '\n--- プロセスがキャンセルされました ---\n';

            consoleLogMap.update(map => ({ ...map, [consoleKey]: map[consoleKey] + logSuffix }));
            consoleStatusMap.update(map => ({ ...map, [consoleKey]: 'CANCELLED' }));

            eventSource.close();
            isRunningProcess.set(false);

            if (onComplete) onComplete(false);
            return;
        }

        consoleLogMap.update(map => {
            const currentLog = map[consoleKey];
            return { ...map, [consoleKey]: currentLog + event.data + '\n' };
        });

        // Auto scroll console if element exists
        setTimeout(() => {
            const consoleEl = document.getElementById(`${consoleKey}-console-log`);
            if (consoleEl) {
                consoleEl.scrollTop = consoleEl.scrollHeight;
            }
        }, 10);
    };

    eventSource.onerror = function(err) {
        consoleLogMap.update(map => ({ ...map, [consoleKey]: map[consoleKey] + '\n[ERROR] 接続エラーまたはサーバーが切断されました。\n' }));
        consoleStatusMap.update(map => ({ ...map, [consoleKey]: 'CONNECTION ERROR' }));
        eventSource.close();
        isRunningProcess.set(false);

        if (onComplete) onComplete(false);
    };

    // Return eventSource and requestId for cancellation support
    return { eventSource, requestId: () => requestId };
}

// Resize panel helper (can be used on mount)
export function initPanelResizer(resizerEl, rightPanelEl) {
    if (!resizerEl || !rightPanelEl) return;

    resizerEl.addEventListener('mousedown', function(e) {
        e.preventDefault();
        resizerEl.classList.add('dragging');
        document.addEventListener('mousemove', resize);
        document.addEventListener('mouseup', stopResize);
    });

    function resize(e) {
        const container = resizerEl.parentElement;
        const containerWidth = container.clientWidth;
        const containerLeft = container.getBoundingClientRect().left;
        
        const rightWidth = containerWidth - (e.clientX - containerLeft);
        
        if (rightWidth >= 300 && rightWidth <= containerWidth * 0.7) {
            rightPanelEl.style.width = rightWidth + 'px';
            rightPanelEl.style.flex = 'none';
        }
    }

    function stopResize() {
        resizerEl.classList.remove('dragging');
        document.removeEventListener('mousemove', resize);
        document.removeEventListener('mouseup', stopResize);
    }
}
