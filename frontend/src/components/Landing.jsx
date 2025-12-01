function Landing({ onSignUp, onLogin }) {
  return (
    <div className="landing-page">
      {/* Section 1: Hero */}
      <section className="landing-hero">
        <div className="hero-content">
          <div className="hero-text">
            <h1>Self-Care Toolkit</h1>
            <p className="hero-tagline">
              Your personalized companion for everyday wellbeing
            </p>
            <button className="primary-button hero-signup-button" onClick={onSignUp}>
              Get Started
            </button>
          </div>
          <div className="hero-image">
            <img src="/image-1.jpeg" alt="Self-care illustration" />
          </div>
        </div>
      </section>

      {/* Section 2: The Problem */}
      <section className="landing-section landing-problem">
        <div className="landing-section-content landing-section-content-reverse">
          <div className="landing-section-text">
            <h2>The Problem</h2>
            <p className="section-text">
              Life can feel overwhelming. Between school, work, relationships, and daily responsibilities, 
              it's easy to lose sight of your own wellbeing. Generic self-care advice doesn't always fit 
              your unique situation, energy level, or preferences.
            </p>
          </div>
          <div className="landing-section-image">
            <img src="/image-2.jpg" alt="Illustration of life challenges" />
          </div>
        </div>
      </section>

      {/* Section 3: Our Solution */}
      <section className="landing-section landing-solution">
        <div className="landing-section-content">
          <div className="landing-section-text">
            <h2>Our Solution</h2>
            <p className="section-text">
              Self-Care Toolkit is an AI-powered companion that learns about you and provides personalized 
              self-care recommendations tailored to your current mood, energy level, and preferences. 
              No one-size-fits-all advice—just thoughtful suggestions that actually work for you.
            </p>
          </div>
          <div className="landing-section-image">
            <img src="/image-3.jpg" alt="Illustration of personalized self-care" />
          </div>
        </div>
      </section>

      {/* Section 4: Features */}
      <section className="landing-section landing-features">
        <h2>What We Offer</h2>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">📝</div>
            <h3>Personalized Quiz</h3>
            <p>Answer a few questions about your current state and receive tailored recommendations</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">💾</div>
            <h3>Save Your Toolkit</h3>
            <p>Build a collection of self-care activities that work for you</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">🤖</div>
            <h3>AI Suggestions</h3>
            <p>Get proactive suggestions based on your patterns and preferences</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">📅</div>
            <h3>Calendar Integration</h3>
            <p>Schedule focused time blocks for your self-care activities</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">📔</div>
            <h3>Journal Entries</h3>
            <p>Reflect with personalized journal prompts in Google Docs</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">🌤️</div>
            <h3>Weather-Aware</h3>
            <p>Get suggestions that match the weather and your environment</p>
          </div>
        </div>
      </section>

      {/* Section 5: AI Powered */}
      <section className="landing-section landing-ai">
        <h2>AI-Powered Personalization</h2>
        <p className="section-text">
          Our intelligent agent learns from your preferences, remembers what works for you, 
          and adapts its suggestions over time. The more you use Self-Care Toolkit, the better 
          it understands how to support your unique wellbeing journey.
        </p>
        <div className="ai-benefits">
          <div className="ai-benefit">
            <strong>Learns Your Patterns</strong>
            <p>Remembers what you accept, decline, and find helpful</p>
          </div>
          <div className="ai-benefit">
            <strong>Respects Your Preferences</strong>
            <p>Adapts to your energy levels, constraints, and likes</p>
          </div>
          <div className="ai-benefit">
            <strong>Grows With You</strong>
            <p>Evolves as your needs and circumstances change</p>
          </div>
        </div>
      </section>

      {/* Section 6: Final CTA */}
      <section className="landing-section landing-cta">
        <h2>Start Your Self-Care Journey</h2>
        <p className="section-text">
          Join us and discover personalized self-care recommendations that truly fit your life.
        </p>
        <div className="cta-buttons">
          <button className="primary-button cta-signup-button" onClick={onSignUp}>
            Sign Up Free
          </button>
          <button className="secondary-button cta-login-button" onClick={onLogin}>
            Log In
          </button>
        </div>
      </section>
    </div>
  )
}

export default Landing

