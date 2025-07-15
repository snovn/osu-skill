/**
 * Global Loader Module
 * Handles loading overlay for navigation and form submissions
 */

class GlobalLoader {
  constructor() {
    this.loader = null;
    this.isActive = false;
    this.timeout = null;
    this.init();
  }

  init() {
    // Create loader element if it doesn't exist
    this.createLoader();
    
    // Bind event listeners when DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.bindEvents());
    } else {
      this.bindEvents();
    }

    // Handle browser back/forward navigation
    this.handlePageVisibility();
  }

  createLoader() {
    // Check if loader already exists
    if (document.getElementById('global-loader')) {
      this.loader = document.getElementById('global-loader');
      return;
    }

    // Create loader HTML
    const loaderHTML = `
      <div id="global-loader">
        <div class="loading">
          <div class="loading-spinner"></div>
          <p class="loading-text">Redirecting...</p>
          <p class="loading-tip">Hang tight while we connect you</p>
        </div>
      </div>
    `;

    // Insert loader at the end of body
    document.body.insertAdjacentHTML('beforeend', loaderHTML);
    this.loader = document.getElementById('global-loader');
  }

  show(message = 'Redirecting...', tip = 'Hang tight while we connect you') {
    if (!this.loader) return;

    // Update text if provided
    const textElement = this.loader.querySelector('.loading-text');
    const tipElement = this.loader.querySelector('.loading-tip');
    
    if (textElement) textElement.textContent = message;
    if (tipElement) tipElement.textContent = tip;

    // Show loader
    this.loader.classList.add('active');
    this.isActive = true;

    // Auto-hide after 10 seconds as failsafe
    this.timeout = setTimeout(() => {
      this.hide();
    }, 10000);
  }

  hide() {
    if (!this.loader) return;

    this.loader.classList.remove('active');
    this.isActive = false;

    // Clear timeout
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
  }

  handlePageVisibility() {
    // Hide loader when page becomes visible (back button, tab switch, etc.)
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        this.hide();
      }
    });

    // Hide loader on page show (back/forward navigation)
    window.addEventListener('pageshow', (event) => {
      // Always hide loader when page is shown
      this.hide();
      
      // If page was loaded from cache (back button), ensure loader is hidden
      if (event.persisted) {
        this.hide();
      }
    });

    // Hide loader when page loads/reloads
    window.addEventListener('load', () => {
      this.hide();
    });

    // Hide loader on popstate (back/forward button)
    window.addEventListener('popstate', () => {
      this.hide();
    });

    // Hide loader on focus (when user returns to tab)
    window.addEventListener('focus', () => {
      this.hide();
    });
  }

  bindEvents() {
    // Handle login/dashboard links
    this.bindNavigationLinks();
    
    // Handle logout links
    this.bindLogoutLinks();
    
    // Handle form submissions (if any)
    this.bindFormSubmissions();
  }
  bindNavigationLinks() {
    const selectors = [
      'a[href="/login"]',
      'a[href="/dashboard"]',
      '.main-login-btn'
    ];

    selectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(link => {
        link.addEventListener('click', (e) => {
          // Don't show loader for same-page links or external links
          if (link.getAttribute('target') === '_blank' || 
              link.getAttribute('href').startsWith('#') ||
              link.getAttribute('href').startsWith('mailto:')) {
            return;
          }

          // Add small delay to ensure the click is processed
          setTimeout(() => {
            this.show('Redirecting...', 'Hang tight while we connect you');
          }, 50);
        });
      });
    });
  }

  bindLogoutLinks() {
    document.querySelectorAll('.logout-link, a[href*="/logout"]').forEach(link => {
      link.addEventListener('click', (e) => {
        // Add small delay to ensure the click is processed
        setTimeout(() => {
          this.show('Logging out...', 'See you next time!');
        }, 50);
      });
    });
  }

  bindFormSubmissions() {
    document.querySelectorAll('form').forEach(form => {
      form.addEventListener('submit', (e) => {
        // Only show loader for forms that aren't search forms
        if (!form.classList.contains('search-form') && 
            !form.getAttribute('action')?.includes('search')) {
          setTimeout(() => {
            this.show('Processing...', 'Please wait while we process your request');
          }, 50);
        }
      });
    });
  }

  // Public methods for manual control
  showWithCustomText(message, tip) {
    this.show(message, tip);
  }

  isVisible() {
    return this.isActive;
  }
}

// Initialize loader when script loads
const globalLoader = new GlobalLoader();

// Export for use in other scripts (if using modules)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = GlobalLoader;
}

// Make available globally
window.GlobalLoader = globalLoader;