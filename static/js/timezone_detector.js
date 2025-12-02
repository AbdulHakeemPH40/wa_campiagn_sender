// Detect user's timezone and store it in a cookie
function detectUserTimezone() {
    try {
        // Get timezone using Intl API
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        // Set cookie with timezone
        document.cookie = "user_timezone=" + timezone + "; path=/; max-age=31536000; SameSite=Lax";
        
        return timezone;
    } catch (error) {
        console.error("Error detecting timezone:", error);
        return "UTC";
    }
}

// Run on page load
document.addEventListener('DOMContentLoaded', detectUserTimezone);