  let leaderboardData = [];
  let currentFilter = 'all';
  let currentLimit = 50;
  let currentUsername = '{{ username or "" }}';
  let loadingTimeout = null;
  let cache = new Map();

  // Cache configuration
  const CACHE_DURATION = 30000; // 30 seconds
  const LOAD_TIMEOUT = 10000;   // 10 seconds

  async function loadLeaderboard(useCache = true) {
    const cacheKey = `leaderboard_${currentFilter}_${currentLimit}`;

    // Check cache
    if (useCache && cache.has(cacheKey)) {
      const cachedData = cache.get(cacheKey);
      if (Date.now() - cachedData.timestamp < CACHE_DURATION) {
        console.log('Using cached leaderboard data');
        leaderboardData = cachedData.data.leaderboard;
        updateStats(cachedData.data.stats);
        renderLeaderboard();
        updateTimestamp(cachedData.data.timestamp);
        return;
      }
    }

    // Show loading
    showLoadingState();

    // Timeout handling
    const timeoutPromise = new Promise((_, reject) => {
      loadingTimeout = setTimeout(() => {
        reject(new Error('Loading timeout - please refresh the page'));
      }, LOAD_TIMEOUT);
    });

    try {
      const fetchPromise = fetch(`/api/leaderboard?verdict=${currentFilter}&limit=${currentLimit}`, {
        method: 'GET',
        headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
      });


      const response = await Promise.race([fetchPromise, timeoutPromise]);

      if (loadingTimeout) clearTimeout(loadingTimeout);
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const data = await response.json();
      if (data.error) throw new Error(data.error);

      cache.set(cacheKey, { data, timestamp: Date.now() });
      cleanCache();

      leaderboardData = data.leaderboard;
      updateStats(data.stats);
      renderLeaderboard();
      updateTimestamp();

    } catch (error) {
      console.error('Leaderboard load error:', error);
      showErrorState(error.message);
    } finally {
      if (loadingTimeout) clearTimeout(loadingTimeout);
    }
  }

  function updateStats(stats) {
    document.getElementById('total-players').textContent = stats.total_players;
    document.getElementById('avg-skill').textContent = stats.avg_skill.toFixed(1);
    document.getElementById('top-skill').textContent = stats.top_skill.toFixed(1);
    document.getElementById('avg-confidence').textContent = stats.avg_confidence.toFixed(1) + '%';
  }

  function showLoadingState() {
    document.getElementById('leaderboard-content').innerHTML = `
      <div class="loading">
        <div class="loading-spinner"></div>
        <p>Loading leaderboard...</p>
        <p class="loading-tip">This may take a moment for the first load</p>
      </div>
    `;
  }

  function showErrorState(message) {
    document.getElementById('leaderboard-content').innerHTML = `
      <div class="empty-state error-state">
        <h3>⚠️ Loading Error</h3>
        <p>${message}</p>
        <button onclick="loadLeaderboard(false)" class="retry-btn">Try Again</button>
        <p class="error-tip">If this continues, please check your connection or try refreshing the page</p>
      </div>
    `;
  }

  function updateTimestamp(customTimestamp = null) {
    const timestamp = customTimestamp || Date.now();
    document.getElementById('last-updated').textContent = 
      `Last updated: ${new Date(timestamp).toLocaleString()}`;
  }

  function cleanCache() {
    const now = Date.now();
    for (const [key, value] of cache.entries()) {
      if (now - value.timestamp > CACHE_DURATION * 2) {
        cache.delete(key);
      }
    }
  }

  function renderLeaderboard() {
    const content = document.getElementById('leaderboard-content');

    let filteredData = leaderboardData;
    if (currentFilter !== 'all') {
      filteredData = leaderboardData.filter(p => p.verdict === currentFilter);
    }

    // Always get your data from the full leaderboard (not the filtered one)
    const currentUserData = leaderboardData.find(p => p.username === currentUsername);

    // Filter other players, excluding yourself
    let otherPlayersData = leaderboardData
      .filter(p => p.username !== currentUsername)
      .filter(p => currentFilter === 'all' || p.verdict === currentFilter)
      .slice(0, currentLimit);


    otherPlayersData = otherPlayersData.slice(0, currentLimit);

    if (filteredData.length === 0) {
      content.innerHTML = `
        <div class="empty-state">
          <h3>No Players Found</h3>
          <p>No players match the current filters.</p>
          <button onclick="loadLeaderboard(false)" class="retry-btn">Refresh Data</button>
        </div>
      `;
      return;
    }

    const fragment = document.createDocumentFragment();

    if (currentUserData) {
      const userSection = document.createElement('div');
      userSection.className = 'leaderboard-section';
      userSection.innerHTML = `
        <h2 class="section-title">Your Position</h2>
        <div class="leaderboard-table current-user-table">
          <div class="table-header current-user-header">
            <div>Rank</div>
            <div>Player</div>
            <div class="recent-skill">Recent</div>
            <div class="peak-skill">Peak</div>
            <div class="skill-match">Match</div>
            <div class="confidence">Confidence</div>
            <div>Verdict</div>
          </div>
          ${renderPlayerRow(currentUserData, true)}
        </div>
      `;
      fragment.appendChild(userSection);
    }

    if (otherPlayersData.length > 0) {
      const leaderboardSection = document.createElement('div');
      leaderboardSection.className = 'leaderboard-section';
      leaderboardSection.innerHTML = `
        <h2 class="section-title">${currentUserData ? 'Global Leaderboard' : 'Leaderboard'}</h2>
        <div class="leaderboard-table">
          <div class="table-header">
            <div>Rank</div>
            <div>Player</div>
            <div class="recent-skill">Recent</div>
            <div class="peak-skill">Peak</div>
            <div class="skill-match">Match</div>
            <div class="confidence">Confidence</div>
            <div>Verdict</div>
          </div>
          ${otherPlayersData.map(p => renderPlayerRow(p, false)).join('')}
        </div>
      `;
      fragment.appendChild(leaderboardSection);
    }

    content.innerHTML = '';
    content.appendChild(fragment);
  }
    function renderPlayerRow(player, isCurrentUser) {
    const rowClass = isCurrentUser ? 'table-row current-user-row' : 'table-row';
    const rankClass = isCurrentUser ? 'rank-cell current-user-rank' : 
                        (player.rank <= 3 ? `rank-cell rank-${player.rank}` : 'rank-cell');
    const nameClass = isCurrentUser ? 'player-name current-user-name' : 'player-name';
    const avatarClass = isCurrentUser ? 'player-avatar current-user-avatar' : 'player-avatar';
    const skillClass = isCurrentUser ? 'skill-cell current-user-skill' : 'skill-cell';

    const isExpired = player.analysis_timestamp && (
        Date.now() - new Date(player.analysis_timestamp).getTime() > 24 * 60 * 60 * 1000
    );

    const verdictLabel = formatVerdict(player.verdict);
    const verdictClass = `verdict-${player.verdict}`;

    let verdictHTML;
    if (isExpired) {
        verdictHTML = `
        <div class="tooltip">
            <span class="verdict-badge ${verdictClass}">${verdictLabel}</span>
            <span class="tooltiptext">Expired</span>
        </div>
        `;
    } else {
        verdictHTML = `<span class="verdict-badge ${verdictClass}">${verdictLabel}</span>`;
    }

    const avatarUrl = player.avatar_url || 'https://a.ppy.sh/14752899?1628953484.png';

    return `
        <div class="${rowClass}">
        <div class="${rankClass}">#${player.rank}</div>
        <div class="player-cell">
            <img src="${avatarUrl}" alt="${player.username}" class="${avatarClass}"
                onerror="this.src='https://a.ppy.sh/14752899?1628953484.png'" />
            <div class="player-info">
            <div class="${nameClass}">
                ${player.username}
                ${isCurrentUser ? '<span class="you-badge">You</span>' : ''}
            </div>
            <div class="player-rank">${player.rank_global ? '#' + player.rank_global.toLocaleString() : 'Unranked'}</div>
            </div>
        </div>
        <div class="${skillClass} recent-skill">${player.recent_skill.toFixed(1)}</div>
        <div class="${skillClass} peak-skill">${player.peak_skill.toFixed(1)}</div>
        <div class="${skillClass} skill-match">${player.skill_match.toFixed(1)}%</div>
        <div class="${skillClass} confidence">${player.confidence.toFixed(1)}%</div>
        <div class="verdict-cell">
            ${verdictHTML}
        </div>
        </div>
    `;
    }


  function formatVerdict(verdict) {
    const verdictMap = {
      'accurate': 'Accurate',
      'slightly_rusty': 'Slightly',
      'rusty': 'Rusty',
      'overranked': 'Overranked',
      'inactive': 'Inactive',
      'insufficient': 'Insufficient',
      'expired': 'Expired'
    };
    return verdictMap[verdict] || verdict;
  }

  // Debounced filter handling
  let filterTimeout = null;

  function handleFilterChange() {
    if (filterTimeout) clearTimeout(filterTimeout);
    filterTimeout = setTimeout(() => {
      currentFilter = document.getElementById('verdict-filter').value;
      currentLimit = parseInt(document.getElementById('limit-filter').value);
      loadLeaderboard(true); // use cache
    }, 300);
  }

  // Filter events
  document.getElementById('verdict-filter').addEventListener('change', handleFilterChange);
  document.getElementById('limit-filter').addEventListener('change', handleFilterChange);

  // Auto-refresh every 5 minutes
  setInterval(() => loadLeaderboard(false), 300000);

  // Initial load
  document.addEventListener('DOMContentLoaded', () => loadLeaderboard(false));

  // Add loading styles
  const style = document.createElement('style');
  style.textContent = `
    .loading {
      text-align: center;
      padding: 60px 20px;
      color: var(--color-text-light);
    }

    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 4px solid rgba(255, 102, 170, 0.3);
      border-top: 4px solid var(--color-primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 20px;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    .loading-tip, .error-tip {
      font-size: 14px;
      opacity: 0.8;
      margin-top: 10px;
    }

    .retry-btn {
      background: var(--color-primary);
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      margin: 10px 0;
      transition: background 0.3s ease;
    }

    .retry-btn:hover {
      background: #e055a3;
    }

    .error-state {
      color: #ff6b6b;
    }

    .error-state h3 {
      color: #ff6b6b;
    }
  `;
  document.head.appendChild(style);