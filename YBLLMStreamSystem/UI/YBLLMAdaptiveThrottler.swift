import QuartzCore
import UIKit

@MainActor
public final class YBLLMAdaptiveThrottler: NSObject {
    public static let shared = YBLLMAdaptiveThrottler()
    public private(set) var allowedToRender = true
    private var link: CADisplayLink?
    private override init() {
        super.init()
        link = CADisplayLink(target: self, selector: #selector(tick(_:)))
        link?.add(to: .main, forMode: .common)
    }
    @objc private func tick(_ link: CADisplayLink) { allowedToRender = link.duration < 0.02 }
    deinit { link?.invalidate() }
}
