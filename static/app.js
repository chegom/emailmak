/**
 * Email Crawler Frontend Application
 */

// DOM Elements
const keywordInput = document.getElementById('keyword');
const startPageInput = document.getElementById('startPage');
const endPageInput = document.getElementById('endPage');
const sourceSelect = document.getElementById('source');
const crawlBtn = document.getElementById('crawlBtn');

const progressSection = document.getElementById('progressSection');
const progressFill = document.getElementById('progressFill');
const progressCount = document.getElementById('progressCount');
const progressStatus = document.getElementById('progressStatus');

const resultsSection = document.getElementById('resultsSection');
const resultsList = document.getElementById('resultsList');
const totalCount = document.getElementById('totalCount');
const emailCount = document.getElementById('emailCount');
const exportBtn = document.getElementById('exportBtn');
const googleSheetBtn = document.getElementById('googleSheetBtn');

// Modal Elements
const sheetModal = document.getElementById('sheetModal');
const sheetUrlInput = document.getElementById('sheetUrlInput');
const sheetCancelBtn = document.getElementById('sheetCancelBtn');
const sheetConfirmBtn = document.getElementById('sheetConfirmBtn');
const botEmailInput = document.getElementById('botEmailInput');
const copyEmailBtn = document.getElementById('copyEmailBtn');

const emptyState = document.getElementById('emptyState');
const stopBtn = document.getElementById('stopBtn');

// State
let results = [];
let abortController = null;
let isCrawling = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
});

function initEventListeners() {
    // 크롤링 버튼 클릭
    crawlBtn.addEventListener('click', startCrawl);

    // Enter 키 입력
    keywordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            startCrawl();
        }
    });

    // CSV 내보내기
    exportBtn.addEventListener('click', exportToCSV);

    // 구글 시트 버튼
    googleSheetBtn.addEventListener('click', async () => {
        if (results.length === 0) {
            showToast('내보낼 결과가 없습니다.', 'warning');
            return;
        }
        sheetModal.classList.remove('hidden');

        // 봇 이메일 로드 (이미 로드되지 않았을 경우)
        if (botEmailInput.value === '로딩중...' || botEmailInput.value === '') {
            try {
                const res = await fetch('/api/config/google-sheet');
                const data = await res.json();
                if (data.service_email) {
                    botEmailInput.value = data.service_email;
                } else {
                    botEmailInput.value = '설정되지 않음 (서버 확인 필요)';
                }
            } catch (e) {
                console.error(e);
                botEmailInput.value = '로드 실패';
            }
        }
    });

    // 봇 이메일 복사
    copyEmailBtn.addEventListener('click', () => {
        const email = botEmailInput.value;
        if (email && !email.includes('로딩') && !email.includes('실패') && !email.includes('설정')) {
            navigator.clipboard.writeText(email).then(() => {
                showToast('봇 이메일이 복사되었습니다.', 'success');
            }).catch(() => {
                botEmailInput.select();
                document.execCommand('copy');
                showToast('봇 이메일이 복사되었습니다.', 'success');
            });
        }
    });

    // 모달 닫기
    sheetCancelBtn.addEventListener('click', () => {
        sheetModal.classList.add('hidden');
    });

    // 모달 오버레이 클릭 시 닫기
    sheetModal.querySelector('.modal-overlay').addEventListener('click', () => {
        sheetModal.classList.add('hidden');
    });

    // 구글 시트 내보내기 확정
    sheetConfirmBtn.addEventListener('click', exportToGoogleSheet);

    // 정지 버튼 클릭
    stopBtn.addEventListener('click', stopCrawl);
}

/**
 * 크롤링 시작
 */
async function startCrawl() {
    const keyword = keywordInput.value.trim();
    const startPage = parseInt(startPageInput.value) || 1;
    const endPage = parseInt(endPageInput.value) || 5;
    const source = sourceSelect.value;

    if (!keyword) {
        showToast('검색어를 입력해주세요.', 'warning');
        keywordInput.focus();
        return;
    }

    if (startPage > endPage) {
        showToast('시작 페이지는 끝 페이지보다 작거나 같아야 합니다.', 'warning');
        startPageInput.focus();
        return;
    }

    if (startPage < 1 || endPage < 1) {
        showToast('페이지 번호는 1 이상이어야 합니다.', 'warning');
        return;
    }

    // AbortController 초기화
    abortController = new AbortController();
    isCrawling = true;

    // UI 상태 변경
    setLoading(true);
    showProgress();
    hideResults();
    results = [];

    // 정지 버튼 활성화
    stopBtn.disabled = false;

    try {
        // SSE 스트리밍으로 크롤링
        await crawlWithStream(keyword, startPage, endPage, source);
    } catch (error) {
        if (error.name === 'AbortError') {
            // 사용자가 정지한 경우
            showToast(`크롤링 정지됨. ${results.length}개 회사 수집됨`, 'warning');
            updateProgress(results.length, results.length, '정지됨');
        } else {
            console.error('Crawl error:', error);
            showToast('크롤링 중 오류가 발생했습니다: ' + error.message, 'error');
        }
    } finally {
        setLoading(false);
        isCrawling = false;
        stopBtn.disabled = true;
        setTimeout(() => hideProgress(), 1000);
        updateResultsCount();
    }
}

/**
 * 크롤링 정지
 */
function stopCrawl() {
    if (abortController && isCrawling) {
        abortController.abort();
        isCrawling = false;
    }
}

/**
 * SSE 스트리밍으로 크롤링
 */
async function crawlWithStream(keyword, startPage, endPage, source) {
    const response = await fetch('/api/crawl/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ keyword, start_page: startPage, end_page: endPage, source }),
        signal: abortController.signal,
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';

    while (true) {
        // 정지 버튼이 눌렸는지 확인
        if (!isCrawling) {
            reader.cancel();
            throw new DOMException('Crawling stopped by user', 'AbortError');
        }

        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE 메시지 파싱
        const lines = buffer.split('\n');
        buffer = lines.pop(); // 마지막 불완전한 라인은 버퍼에 유지

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.slice(6));
                    handleStreamMessage(data);
                } catch (e) {
                    console.warn('Failed to parse SSE message:', line);
                }
            }
        }
    }
}

/**
 * 스트림 메시지 처리
 */
function handleStreamMessage(data) {
    switch (data.type) {
        case 'start':
            updateProgress(0, data.total, '회사 정보를 수집하는 중입니다...');
            showResults();
            break;

        case 'progress':
            updateProgress(data.current, data.total, `${data.company.company_name} 처리 중...`);
            addResult(data.company);
            break;

        case 'complete':
            updateProgress(data.total, data.total, '크롤링 완료!');
            setTimeout(() => hideProgress(), 1000);
            updateResultsCount();
            showToast(`크롤링 완료! ${results.length}개 회사 수집됨`, 'success');
            break;

        case 'error':
            showToast(data.message, 'error');
            hideProgress();
            break;
    }
}

/**
 * 진행 상태 업데이트
 */
function updateProgress(current, total, status) {
    const percent = total > 0 ? (current / total) * 100 : 0;
    progressFill.style.width = `${percent}%`;
    progressCount.textContent = `${current} / ${total}`;
    progressStatus.textContent = status;
}

/**
 * 결과 추가
 */
function addResult(company) {
    results.push(company);

    const hasEmail = company.emails && company.emails.length > 0;

    const card = document.createElement('div');
    card.className = `result-card ${hasEmail ? 'has-email' : ''}`;

    card.innerHTML = `
        <div class="result-header">
            <div>
                <div class="company-name">${escapeHtml(company.company_name)}</div>
                ${company.job_title ? `<div class="job-title">${escapeHtml(company.job_title)}</div>` : ''}
            </div>
            <div class="result-links">
                ${getSourceLinks(company)}
                ${company.homepage ? `<a href="${escapeHtml(company.homepage)}" target="_blank" class="link-btn">🌐 홈페이지</a>` : ''}
            </div>
        </div>
        <div class="email-list">
            ${hasEmail
            ? company.emails.map(email => `
                    <span class="email-tag" onclick="copyEmail('${escapeHtml(email)}')">
                        ${escapeHtml(email)}
                        <span class="copy-icon">📋</span>
                    </span>
                `).join('')
            : '<span class="no-email">이메일을 찾지 못했습니다</span>'
        }
        </div>
    `;

    resultsList.appendChild(card);
    updateResultsCount();
}

/**
 * 결과 수 업데이트
 */
function updateResultsCount() {
    const total = results.length;
    const withEmail = results.filter(r => r.emails && r.emails.length > 0).length;
    const totalEmails = results.reduce((sum, r) => sum + (r.emails ? r.emails.length : 0), 0);

    totalCount.textContent = `${total}개 회사`;
    emailCount.textContent = `이메일 ${totalEmails}개`;
}

/**
 * 소스별 링크 생성
 */
function getSourceLinks(company) {
    const source = company.source || 'saramin';
    let links = '';

    if (source === 'jobkorea') {
        // 잡코리아: job_url(채용공고)과 company_url(회사정보) 모두 표시
        if (company.job_url) {
            links += `<a href="${escapeHtml(company.job_url)}" target="_blank" class="link-btn">📋 잡코리아</a>`;
        }
        if (company.company_url) {
            links += `<a href="${escapeHtml(company.company_url)}" target="_blank" class="link-btn">🏢 회사정보</a>`;
        }
    } else if (source === 'wanted') {
        // 원티드
        if (company.company_url) {
            links += `<a href="${escapeHtml(company.company_url)}" target="_blank" class="link-btn">🇼 원티드</a>`;
        }
    } else {
        // 사람인
        if (company.company_url) {
            links += `<a href="${escapeHtml(company.company_url)}" target="_blank" class="link-btn">📋 사람인</a>`;
        }
    }

    return links;
}

/**
 * 이메일 복사
 */
function copyEmail(email) {
    navigator.clipboard.writeText(email).then(() => {
        showToast(`${email} 복사됨!`, 'success');
    }).catch(() => {
        showToast('복사 실패', 'error');
    });
}

/**
 * CSV 내보내기
 */
function exportToCSV() {
    if (results.length === 0) {
        showToast('내보낼 데이터가 없습니다.', 'warning');
        return;
    }

    // CSV 헤더 (구글 시트와 동일)
    const headers = ['회사명', '채용공고 제목', '대표 이메일', '추가 이메일', '홈페이지', '채용사이트 링크', '기업정보 링크', '수집 출처', '수집 날짜'];

    // CSV 데이터
    const today = new Date().toISOString().slice(0, 10);
    const rows = results.map(r => {
        const emails = r.emails || [];
        return [
            r.company_name || '',
            r.job_title || '',
            emails[0] || '',
            emails.slice(1).join(', '),
            r.homepage || '',
            r.job_url || '',
            r.company_url || '',
            r.source || '',
            today
        ];
    });

    // CSV 문자열 생성
    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(','))
    ].join('\n');

    // BOM 추가 (한글 지원)
    const bom = '\uFEFF';
    const blob = new Blob([bom + csvContent], { type: 'text/csv;charset=utf-8;' });

    // 다운로드
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `email_crawl_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();

    showToast('CSV 파일 다운로드 완료!', 'success');
}

/**
 * 구글 시트로 내보내기
 */
async function exportToGoogleSheet() {
    const sheetUrl = sheetUrlInput.value.trim();

    if (!sheetUrl) {
        showToast('유효한 구글 시트 URL을 입력해주세요.', 'warning');
        return;
    }

    // 버튼 로딩 상태
    const originalText = sheetConfirmBtn.innerText;
    sheetConfirmBtn.innerText = '내보내는 중...';
    sheetConfirmBtn.disabled = true;

    // 현재 검색어와 출처 가져오기
    const keyword = document.getElementById('keyword').value.trim() || '검색어없음';
    const sourceSelect = document.getElementById('source');
    const sourceText = sourceSelect.options[sourceSelect.selectedIndex].text;

    try {
        const response = await fetch('/api/export/sheet', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                sheet_url: sheetUrl,
                companies: results,
                keyword: keyword,
                source: sourceText
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast(data.message, 'success');
            sheetModal.classList.add('hidden');
            sheetUrlInput.value = ''; // 초기화
        } else {
            showToast(data.detail || '내보내기에 실패했습니다.', 'error');
        }
    } catch (error) {
        showToast('서버 연결 오류가 발생했습니다.', 'error');
        console.error(error);
    } finally {
        sheetConfirmBtn.innerText = originalText;
        sheetConfirmBtn.disabled = false;
    }
}

/**
 * UI 헬퍼 함수들
 */
function setLoading(loading) {
    crawlBtn.disabled = loading;
    if (loading) {
        crawlBtn.classList.add('loading');
    } else {
        crawlBtn.classList.remove('loading');
    }
}

function showProgress() {
    progressSection.classList.remove('hidden');
    emptyState.classList.add('hidden');
    progressFill.style.width = '0%';
}

function hideProgress() {
    progressSection.classList.add('hidden');
}

function showResults() {
    resultsSection.classList.remove('hidden');
    emptyState.classList.add('hidden');
    resultsList.innerHTML = '';
}

function hideResults() {
    resultsSection.classList.add('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 토스트 메시지
 */
function showToast(message, type = 'info') {
    // 기존 토스트 제거
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        padding: 12px 24px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#6366f1'};
        color: white;
        border-radius: 8px;
        font-weight: 500;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        z-index: 1000;
        animation: slideUp 0.3s ease;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 애니메이션 스타일 추가
const style = document.createElement('style');
style.textContent = `
    @keyframes slideUp {
        from { opacity: 0; transform: translateX(-50%) translateY(20px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
    @keyframes fadeOut {
        to { opacity: 0; transform: translateX(-50%) translateY(-10px); }
    }
`;
document.head.appendChild(style);
