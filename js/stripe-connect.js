Liberapay.stripe_connect = {};

Liberapay.stripe_connect.init = function() {
    var container = document.getElementById('stripe-connect');
    if (!container) return;

    async function fetchClientSecret() {
        try {
            var response = await fetch('', {
                headers: {
                    "Accept": "application/json",
                    "X-CSRF-TOKEN": container.dataset.csrfToken,
                },
                method: "POST",
            });
            if (response.ok) {
                return (await response.json()).client_secret;
            } else {
                Liberapay.error(response.status);
            }
        } catch(exc) {
            Liberapay.error(exc);
            return undefined;
        }
    };

    const self = Liberapay.stripe_connect;
    self.components = {};
    const component_nav = document.getElementById('stripe-component-nav');
    var target_component_name;
    if (component_nav) {
        target_component_name = 'account-management';
        component_nav.querySelector(
            'a[data-component="' + target_component_name + '"]'
        ).parentElement.classList.add('active');
        component_nav.classList.remove('hidden');
        const component_nav_links = component_nav.querySelectorAll('a');
        component_nav_links.forEach((a) => {
            a.addEventListener('click', (e) => {
                e.preventDefault();
                component_nav_links.forEach((a) => {
                    a.parentElement.classList.remove('active')
                });
                a.parentElement.classList.add('active');
                const component_name = a.dataset.component;
                if (self.components[component_name]) {
                    self.components[component_name].classList.remove('hidden');
                } else {
                    self.components[component_name] = self.instance.create(
                        component_name
                    );
                    container.appendChild(self.components[component_name]);
                }
                self.current_component.classList.add('hidden');
                self.current_component = self.components[component_name];
                container.scrollIntoView();
            });
        });
    } else {
        target_component_name = 'account-onboarding';
    }

    if (!window.StripeConnect) {
        alert(container.dataset.msgStripeMissing);
        return;
    }
    StripeConnect.onLoad = () => {
        self.instance = StripeConnect.init({
            appearance: {
                variables: {
                    colorPrimary: '#337ab7',
                    colorText: rgb_to_hex($(container).css('color')),
                    fontFamily: $(container).css('font-family'),
                    fontSizeBase: $(container).css('font-size'),
                },
            },
            fetchClientSecret: fetchClientSecret,
            fonts: [{cssSrc: 'https://liberapay.com/assets/fonts.css'}],
            locale: document.documentElement.getAttribute('lang'),
            publishableKey: container.dataset.stripePubKey,
        });
        const notification_div = document.getElementById('stripe-notification');
        if (notification_div) {
            notification_div.appendChild(self.instance.create('notification-banner'));
        }
        var component = self.instance.create(target_component_name);
        self.current_component = self.components[target_component_name] = component;
        if (target_component_name == 'account-onboarding') {
            component.setOnExit(() => {
                window.location.href = location.href;
            });
        }
        container.appendChild(self.current_component);
    }
};
