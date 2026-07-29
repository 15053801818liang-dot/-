import UIKit

@MainActor
final class ChatViewController: UIViewController {
    private let textView = UITextView()
    private let renderer = YBLLMTypewriterRenderer.shared

    override func viewDidLoad() {
        super.viewDidLoad()
        setupUI()
        renderer.onUpdate = { [weak self] in self?.textView.text = $0 }
        Task { await runDemo() }
    }

    private func runDemo() async {
        do {
            for try await step in YBLLMAgentRunner.shared.run(goal: "解释 GCD 的 happens-before", environment: .release) {
                await renderer.push(step.thought)
                if case .answer(let text) = step.action { await renderer.push(text) }
                if let observation = step.observation { await renderer.push("观察: " + observation) }
            }
        } catch { await renderer.push("错误: \(error.localizedDescription)") }
        renderer.finish()
    }

    private func setupUI() {
        view.backgroundColor = .systemBackground
        view.addSubview(textView)
        textView.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            textView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            textView.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            textView.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            textView.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16)
        ])
        textView.isEditable = false
        textView.font = .systemFont(ofSize: 16)
        textView.backgroundColor = .systemBackground
        textView.textColor = .label
    }
}
