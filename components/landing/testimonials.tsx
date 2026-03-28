const testimonials = [
  {
    quote:
      "Metalyzi has completely changed how I evaluate properties. What used to take me hours with spreadsheets now takes 30 seconds.",
    name: "James Thornton",
    title: "Buy-to-Let Investor, Manchester",
    initials: "JT",
  },
  {
    quote:
      "The AI insights flagged a risk I hadn't considered on a deal I was about to commit to. That alone saved me thousands.",
    name: "Sarah Mitchell",
    title: "Portfolio Landlord, London",
    initials: "SM",
  },
  {
    quote:
      "I recommend Metalyzi to every client looking at investment properties. The reports are professional and the SDLT calculations are spot on.",
    name: "David Chen",
    title: "Property Consultant, Birmingham",
    initials: "DC",
  },
]

export function Testimonials() {
  return (
    <section className="border-y border-border/50 bg-card/30 py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Trusted by UK Investors
          </h2>
          <p className="mt-4 text-pretty text-lg leading-relaxed text-muted-foreground">
            Join thousands of property investors making data-driven decisions.
          </p>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-3">
          {testimonials.map((testimonial) => (
            <div
              key={testimonial.name}
              className="flex flex-col rounded-xl border border-border/50 bg-card p-6"
            >
              <blockquote className="flex-1 text-sm leading-relaxed text-muted-foreground">
                {'"'}{testimonial.quote}{'"'}
              </blockquote>
              <div className="mt-6 flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                  {testimonial.initials}
                </div>
                <div>
                  <div className="text-sm font-medium text-foreground">
                    {testimonial.name}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {testimonial.title}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
