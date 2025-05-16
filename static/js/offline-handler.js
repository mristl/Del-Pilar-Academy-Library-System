document.addEventListener('DOMContentLoaded', function() {
    console.log("DEBUG: DOM Content Loaded. Initializing offline check.");

    const formToSubmit = document.getElementById('main-form');
    const networkErrorMessage = document.getElementById('network-error-message');

    console.log("DEBUG: Found form element:", formToSubmit);
    console.log("DEBUG: Found error message element:", networkErrorMessage);

    if (formToSubmit && networkErrorMessage) {
        console.log("DEBUG: Attaching submit event listener to form.");

        formToSubmit.addEventListener('submit', function(event) {
            console.log("DEBUG: Submit event detected on form.");
            console.log("DEBUG: Checking navigator.onLine status:", navigator.onLine);

            if (!navigator.onLine) {
                console.log("DEBUG: Condition !navigator.onLine is TRUE. Preventing default submission.");
                event.preventDefault(); // Stop the form submission
                networkErrorMessage.style.display = 'block'; // Show the message
                console.log("DEBUG: Network error message should be visible.");
                // Returning false can also sometimes help ensure submission stops in older browsers, though preventDefault is standard.
                return false;
            } else {
                console.log("DEBUG: Condition !navigator.onLine is FALSE. Allowing default submission.");
                networkErrorMessage.style.display = 'none'; // Ensure message is hidden if online
            }
        });
    } else {
        console.error("DEBUG: ERROR - Could not find form (#main-form) or error message div (#network-error-message). Event listener not attached.");
    }

    // Global online/offline listeners for additional debugging
    window.addEventListener('offline', () => {
        console.log("DEBUG: Browser window detected OFFLINE event.");
    });

    window.addEventListener('online', () => {
         console.log("DEBUG: Browser window detected ONLINE event.");
         if(networkErrorMessage) {
            networkErrorMessage.style.display = 'none';
         }
    });

});