// Notification display
const showNotification = () => {
    notification.classList.add('show');
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
};

// Function to scroll chat to bottom
function scrollToBottom(element) {
    // Use smooth scrolling for better UX
    element.scrollTo({
        top: element.scrollHeight,
        behavior: 'smooth'
    });
};

$(document).ready(function() {
    // Scroll to bottom of chat on load
    scrollToBottom(chatLog);
    // Add a MutationObserver to ensure chat scrolls down when new content is added
    const chatObserver = new MutationObserver(function(mutations) {
        scrollToBottom(chatLog);
    });
    
    // Start observing the chat container for added nodes
    chatObserver.observe(chatLog, { childList: true });
});
