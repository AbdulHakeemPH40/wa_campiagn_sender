/**
 * Global Loading Manager for WA Campaign Sender
 * Handles loading animations across all apps (sitevisitor, userpanel, adminpanel)
 */

class LoadingManager {
    constructor() {
        this.isLoading = false;
        this.loadingQueue = new Set();
        this.delayedLoadingTimer = null;
        this.forcedLoadingTimer = null;
        this.pageLoadStartTime = Date.now();
        this.init();
    }

    init() {
        this.createPageLoadingOverlay();
        this.bindGlobalEvents();
        this.handlePageLoad();
        
        // Failsafe: Ensure loading is hidden on initialization
        this._ensureLoadingHidden();
    }

    // Create main page loading overlay
    createPageLoadingOverlay() {
        if (document.getElementById('page-loading-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'page-loading-overlay';
        overlay.className = 'page-loading-overlay';
        
        // Determine app type for themed loading
        const appType = this.detectAppType();
        if (appType) {
            overlay.classList.add(`${appType}-loading`);
        }

        overlay.innerHTML = `
            <div class="loading-content text-center">
                <div class="loader loader-large"></div>
                <div class="loading-text pulse-text">Loading...</div>
            </div>
        `;

        // Start hidden by default
        overlay.classList.add('hidden');
        document.body.appendChild(overlay);
    }

    // Detect which app we're in based on URL or body classes
    detectAppType() {
        const path = window.location.pathname;
        const bodyClasses = document.body.className;

        if (path.includes('/admin/') || bodyClasses.includes('adminpanel')) {
            return 'adminpanel';
        } else if (path.includes('/dashboard/') || path.includes('/user/') || bodyClasses.includes('userpanel')) {
            return 'userpanel';
        } else {
            return 'sitevisitor';
        }
    }

    // Show page loading overlay with optional delay
    showPageLoading(message = 'Loading...', forceShow = false) {
        if (forceShow) {
            this._showPageLoadingImmediate(message);
        } else {
            this._showPageLoadingDelayed(message);
        }
    }

    // Show loading immediately (for forced scenarios)
    _showPageLoadingImmediate(message) {
        const overlay = document.getElementById('page-loading-overlay');
        if (overlay) {
            const loadingText = overlay.querySelector('.loading-text');
            if (loadingText) {
                loadingText.textContent = message;
            }
            overlay.classList.remove('hidden');
            this.isLoading = true;
        }
    }

    // Show loading only after 5 seconds delay (smart loading)
    _showPageLoadingDelayed(message) {
        // Clear any existing delayed timer
        if (this.delayedLoadingTimer) {
            clearTimeout(this.delayedLoadingTimer);
        }

        // Set timer to show loading after 5 seconds
        this.delayedLoadingTimer = setTimeout(() => {
            if (!this.isLoading) {
                this._showPageLoadingImmediate(message);
            }
        }, 5000);
    }

    // Hide page loading overlay
    hidePageLoading() {
        // Clear any pending delayed loading
        if (this.delayedLoadingTimer) {
            clearTimeout(this.delayedLoadingTimer);
            this.delayedLoadingTimer = null;
        }

        // Clear any forced loading timer
        if (this.forcedLoadingTimer) {
            clearTimeout(this.forcedLoadingTimer);
            this.forcedLoadingTimer = null;
        }

        const overlay = document.getElementById('page-loading-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
            setTimeout(() => {
                this.isLoading = false;
            }, 300);
        }
    }

    // Show button loading state
    showButtonLoading(button, originalText = null) {
        if (!button) return;

        const btnText = button.querySelector('.btn-text') || button;
        if (!originalText) {
            originalText = btnText.textContent.trim();
        }
        
        button.setAttribute('data-original-text', originalText);
        button.classList.add('btn-loading');
        button.disabled = true;

        // Add to loading queue
        this.loadingQueue.add(button);
    }

    // Hide button loading state
    hideButtonLoading(button) {
        if (!button) return;

        const originalText = button.getAttribute('data-original-text');
        if (originalText) {
            const btnText = button.querySelector('.btn-text') || button;
            btnText.textContent = originalText;
        }

        button.classList.remove('btn-loading');
        button.disabled = false;
        button.removeAttribute('data-original-text');

        // Remove from loading queue
        this.loadingQueue.delete(button);
    }

    // Show form loading overlay
    showFormLoading(form, message = 'Processing...') {
        if (!form) return;

        // Make form container relative if not already
        if (getComputedStyle(form).position === 'static') {
            form.style.position = 'relative';
        }

        // Remove existing overlay
        const existingOverlay = form.querySelector('.form-loading-overlay');
        if (existingOverlay) {
            existingOverlay.remove();
        }

        const overlay = document.createElement('div');
        overlay.className = 'form-loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content text-center">
                <div class="loader"></div>
                <div class="loading-text">${message}</div>
            </div>
        `;

        form.appendChild(overlay);
    }

    // Hide form loading overlay
    hideFormLoading(form) {
        if (!form) return;

        const overlay = form.querySelector('.form-loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }

    // Show table loading
    showTableLoading(table, message = 'Loading data...') {
        if (!table) return;

        table.classList.add('table-loading');

        const existingOverlay = table.querySelector('.table-loading-overlay');
        if (existingOverlay) {
            existingOverlay.remove();
        }

        const overlay = document.createElement('div');
        overlay.className = 'table-loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content text-center">
                <div class="dots-loader">
                    <div></div>
                    <div></div>
                    <div></div>
                    <div></div>
                </div>
                <div class="loading-text">${message}</div>
            </div>
        `;

        table.appendChild(overlay);
    }

    // Hide table loading
    hideTableLoading(table) {
        if (!table) return;

        table.classList.remove('table-loading');
        const overlay = table.querySelector('.table-loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }

    // Show card loading animation
    showCardLoading(card) {
        if (!card) return;
        card.classList.add('card-loading');
    }

    // Hide card loading animation
    hideCardLoading(card) {
        if (!card) return;
        card.classList.remove('card-loading');
    }

    // Handle page load events with smart loading
    handlePageLoad() {
        this.pageLoadStartTime = Date.now();
        
        // DON'T show loading immediately - only if page is slow
        // Start the 5-second timer to check if page is slow
        this._startSlowPageDetection();

        // Hide loading when page is fully loaded
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this._onPageLoadComplete();
            });
        } else {
            this._onPageLoadComplete();
        }

        // Handle window load for additional resources
        window.addEventListener('load', () => {
            this._onPageLoadComplete();
        });
    }

    // Start slow page detection timer
    _startSlowPageDetection() {
        // Clear any existing timer
        if (this.delayedLoadingTimer) {
            clearTimeout(this.delayedLoadingTimer);
        }

        // Set timer to show loading only if page takes more than 5 seconds
        this.delayedLoadingTimer = setTimeout(() => {
            // Page is taking too long, show loading now
            this._showPageLoadingImmediate('Loading page...');
        }, 5000);
    }

    // Handle page load completion
    _onPageLoadComplete() {
        // Clear the slow page detection timer
        if (this.delayedLoadingTimer) {
            clearTimeout(this.delayedLoadingTimer);
            this.delayedLoadingTimer = null;
        }

        // If loading is currently showing, hide it
        if (this.isLoading) {
            setTimeout(() => {
                this.hidePageLoading();
            }, 500); // Small delay to show completion
        }
    }

    // Failsafe method to ensure loading is hidden on initialization
    _ensureLoadingHidden() {
        setTimeout(() => {
            const overlay = document.getElementById('page-loading-overlay');
            if (overlay && !overlay.classList.contains('hidden')) {
                // Force hide if it's visible without proper loading state
                overlay.classList.add('hidden');
                this.isLoading = false;
            }
        }, 1000); // Wait 1 second after initialization
    }

    // Bind global events
    bindGlobalEvents() {
        // Handle form submissions
        document.addEventListener('submit', (e) => {
            const form = e.target;
            if (form.tagName === 'FORM' && !form.hasAttribute('data-no-loading')) {
                this.showFormLoading(form, 'Submitting...');
                
                // Auto-hide after timeout as fallback
                setTimeout(() => {
                    this.hideFormLoading(form);
                }, 30000);
            }
        });

        // Handle button clicks with loading attribute
        document.addEventListener('click', (e) => {
            const button = e.target.closest('[data-loading]');
            if (button) {
                const loadingText = button.getAttribute('data-loading') || 'Loading...';
                this.showButtonLoading(button);
                
                // Auto-hide after timeout as fallback
                setTimeout(() => {
                    this.hideButtonLoading(button);
                }, 15000);
            }
        });

        // Handle AJAX requests (if using jQuery) - Smart loading
        if (typeof $ !== 'undefined') {
            $(document).ajaxStart(() => {
                if (!this.isLoading && !this.isForcedLoadingActive()) {
                    // Use smart loading for AJAX requests
                    this.showPageLoading('Processing request...');
                }
            });

            $(document).ajaxStop(() => {
                // Only hide if not in forced loading mode
                if (!this.isForcedLoadingActive()) {
                    this.hidePageLoading();
                }
            });

            $(document).ajaxError(() => {
                // Always hide on error, even if forced loading
                this.hidePageLoading();
                this.hideAllLoadingStates();
            });
        }

        // Handle fetch requests
        this.interceptFetch();

        // Handle navigation - REMOVED automatic loading on beforeunload
        // This was causing irritating loading animations on every navigation
        
        // Handle back/forward navigation - Use smart loading
        window.addEventListener('popstate', () => {
            this.pageLoadStartTime = Date.now();
            this._startSlowPageDetection();
        });
    }

    // Intercept fetch requests to show smart loading
    interceptFetch() {
        const originalFetch = window.fetch;
        window.fetch = (...args) => {
            // Only show loading for fetch if not already loading and not forced
            if (!this.isLoading && !this.isForcedLoadingActive()) {
                // Use smart loading for fetch requests
                this.showPageLoading('Fetching data...');
            }

            return originalFetch(...args)
                .then(response => {
                    // Only hide if not in forced loading mode
                    if (!this.isForcedLoadingActive()) {
                        this.hidePageLoading();
                    }
                    return response;
                })
                .catch(error => {
                    // Always hide on error, even if forced loading
                    this.hidePageLoading();
                    this.hideAllLoadingStates();
                    throw error;
                });
        };
    }

    // Hide all loading states (emergency cleanup)
    hideAllLoadingStates() {
        this.hidePageLoading();
        
        // Hide all button loading states
        this.loadingQueue.forEach(button => {
            this.hideButtonLoading(button);
        });
        this.loadingQueue.clear();

        // Hide all form loading overlays
        document.querySelectorAll('.form-loading-overlay').forEach(overlay => {
            overlay.remove();
        });

        // Hide all table loading overlays
        document.querySelectorAll('.table-loading-overlay').forEach(overlay => {
            overlay.remove();
        });
        document.querySelectorAll('.table-loading').forEach(table => {
            table.classList.remove('table-loading');
        });

        // Hide all card loading animations
        document.querySelectorAll('.card-loading').forEach(card => {
            card.classList.remove('card-loading');
        });
    }

    // Utility methods for specific scenarios
    showPaymentLoading() {
        this.showPageLoading('Processing payment...', true);
    }

    showSubscriptionLoading() {
        this.showPageLoading('Updating subscription...', true);
    }

    showDashboardLoading() {
        this.showPageLoading('Loading dashboard...');
    }

    showAuthLoading() {
        this.showPageLoading('Authenticating...', true);
    }

    // Forced loading methods for specific actions (3-5 seconds minimum)
    showTrialActivationLoading() {
        this._showPageLoadingImmediate('Activating free trial...');
        this._setForcedLoadingTimer(4000); // 4 seconds minimum
    }

    showProActivationLoading() {
        this._showPageLoadingImmediate('Activating PRO subscription...');
        this._setForcedLoadingTimer(5000); // 5 seconds minimum
    }

    showSettingsUpdateLoading() {
        this._showPageLoadingImmediate('Updating settings...');
        this._setForcedLoadingTimer(3000); // 3 seconds minimum
    }

    showProfileUpdateLoading() {
        this._showPageLoadingImmediate('Updating profile...');
        this._setForcedLoadingTimer(3000); // 3 seconds minimum
    }

    showNumberUpdateLoading() {
        this._showPageLoadingImmediate('Updating WhatsApp numbers...');
        this._setForcedLoadingTimer(3500); // 3.5 seconds minimum
    }

    // Set forced loading timer to prevent early hiding
    _setForcedLoadingTimer(duration) {
        if (this.forcedLoadingTimer) {
            clearTimeout(this.forcedLoadingTimer);
        }
        
        this.forcedLoadingTimer = setTimeout(() => {
            this.forcedLoadingTimer = null;
            // Don't auto-hide here, let the actual process completion hide it
        }, duration);
    }

    // Check if forced loading is active
    isForcedLoadingActive() {
        return this.forcedLoadingTimer !== null;
    }

    // Method to manually trigger loading for specific elements
    addLoadingToElement(element, type = 'spinner', message = 'Loading...') {
        if (!element) return;

        element.style.position = 'relative';
        element.style.minHeight = '100px';

        const loadingHtml = this.getLoadingHtml(type, message);
        element.innerHTML = loadingHtml;
    }

    // Get loading HTML based on type
    getLoadingHtml(type, message) {
        const loadingTypes = {
            spinner: `
                <div class="d-flex justify-content-center align-items-center" style="min-height: 100px;">
                    <div class="text-center">
                        <div class="spinner"></div>
                        <div class="loading-text">${message}</div>
                    </div>
                </div>
            `,
            dots: `
                <div class="d-flex justify-content-center align-items-center" style="min-height: 100px;">
                    <div class="text-center">
                        <div class="dots-loader">
                            <div></div>
                            <div></div>
                            <div></div>
                            <div></div>
                        </div>
                        <div class="loading-text">${message}</div>
                    </div>
                </div>
            `,
            pulse: `
                <div class="d-flex justify-content-center align-items-center" style="min-height: 100px;">
                    <div class="text-center">
                        <div class="pulse-loader"></div>
                        <div class="loading-text">${message}</div>
                    </div>
                </div>
            `,
            progress: `
                <div class="d-flex justify-content-center align-items-center" style="min-height: 100px;">
                    <div class="text-center">
                        <div class="progress-loader"></div>
                        <div class="loading-text">${message}</div>
                    </div>
                </div>
            `
        };

        return loadingTypes[type] || loadingTypes.spinner;
    }
}

// IMMEDIATE FIX: Hide any stuck loading overlays
(function() {
    // Run immediately when script loads
    const hideStuckLoading = () => {
        const overlay = document.getElementById('page-loading-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
        // Also check for any overlay without ID
        const overlays = document.querySelectorAll('.page-loading-overlay');
        overlays.forEach(o => o.classList.add('hidden'));
    };
    
    // Hide immediately
    hideStuckLoading();
    
    // Hide again after a short delay
    setTimeout(hideStuckLoading, 100);
    
    // Hide when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', hideStuckLoading);
    } else {
        hideStuckLoading();
    }
})();

// Initialize loading manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.loadingManager = new LoadingManager();
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LoadingManager;
}
