describe('Test the homepage', function () {

  beforeEach(function () {
    browser().navigateTo('/');
  });

  it('should render copy correctly', function () {
    expect(element('h2.top span').text()).toContain('Weekly Cash Gifts');
    expect(element('h1 span').text()).toContain('Inspiring Generosity');
  });

});
