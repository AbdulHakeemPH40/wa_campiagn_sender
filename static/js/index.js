document.addEventListener('DOMContentLoaded', () => {
    // Demo Modal Elements
    const watchDemoBtn = document.getElementById('watchDemoBtn');
    const demoModal = document.getElementById('demoModal');
    const closeModalBtn = document.getElementById('closeModal');
    const modalGetStarted = document.getElementById('modalGetStarted'); 
    const modalLearnMore = document.getElementById('modalLearnMore'); 

    // Function to hide the demo modal and stop video
    function hideDemoModal() {
        if (demoModal) {
            demoModal.classList.add('hidden');
            const iframe = demoModal.querySelector('iframe');
            if (iframe) {
                const iframeSrc = iframe.src;
                iframe.src = iframeSrc; // Reloads iframe to stop video
            }
        }
    }

    // Event listener for opening the demo modal
    if (watchDemoBtn) {
        watchDemoBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (demoModal) {
                demoModal.classList.remove('hidden');
            }
        });
    }

    // Event listener for closing the modal via button
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            hideDemoModal();
        });
    }

    // Event listeners for modal interactions (overlay click, Esc key)
    if (demoModal) {
        demoModal.addEventListener('click', (event) => {
            if (event.target === demoModal) { // Click on overlay
                hideDemoModal();
            }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !demoModal.classList.contains('hidden')) {
                hideDemoModal();
            }
        });
    }

    // Event listeners for buttons inside the modal (with smooth scroll)
    if (modalGetStarted) {
        modalGetStarted.addEventListener('click', (e) => {
            e.preventDefault();
            hideDemoModal();
            const targetId = modalGetStarted.getAttribute('href');
            if (targetId && targetId.startsWith('#')) {
                const targetElement = document.querySelector(targetId);
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    }
    if (modalLearnMore) {
        modalLearnMore.addEventListener('click', (e) => {
            e.preventDefault();
            hideDemoModal();
            const targetId = modalLearnMore.getAttribute('href');
            if (targetId && targetId.startsWith('#')) {
                const targetElement = document.querySelector(targetId);
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    }

    // Testimonial Slider
    const slider = document.getElementById('testimonialSlider');
    if (slider) {
        const slides = slider.querySelectorAll('.testimonial-slide');
        const navButtons = slider.querySelectorAll('[data-slide]');
        let currentSlide = 0;
        let autoSlideInterval;

        function showSlide(index) {
            slides.forEach((slide, i) => {
                slide.classList.add('hidden', 'opacity-0');
                if (i === index) {
                    slide.classList.remove('hidden');
                    setTimeout(() => slide.classList.remove('opacity-0'), 10);
                }
            });
            navButtons.forEach((button, i) => {
                button.classList.remove('bg-primary', 'w-4');
                button.classList.add('bg-gray-300', 'w-3');
                if (i === index) {
                    button.classList.add('bg-primary', 'w-4');
                    button.classList.remove('bg-gray-300', 'w-3');
                }
            });
            currentSlide = index;
        }

        function startAutoSlide() {
            stopAutoSlide();
            autoSlideInterval = setInterval(() => {
                currentSlide = (currentSlide + 1) % slides.length;
                showSlide(currentSlide);
            }, 5000);
        }

        function stopAutoSlide() {
            clearInterval(autoSlideInterval);
        }

        navButtons.forEach(button => {
            button.addEventListener('click', () => {
                showSlide(parseInt(button.dataset.slide));
                stopAutoSlide();
                startAutoSlide();
            });
        });

        if (slides.length > 0) {
            showSlide(0);
            startAutoSlide();
        }
    }

    // Smooth Scrolling for Navigation Links
    const navLinks = document.querySelectorAll('header nav a[href^="#"], footer a[href^="#"], a.hero-section-button[href^="#"]');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if (targetId && targetId.startsWith('#')) {
                const targetElement = document.querySelector(targetId);
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    });
});
