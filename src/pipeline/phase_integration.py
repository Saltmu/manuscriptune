from src.utils.ai_exceptions import IntegrationError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class IntegrationPhase:
    """Phase responsible for integrating review findings and generating the final report."""

    def __init__(self, model: str, output_dir: str):
        self.model = model
        self.output_dir = output_dir

    def integrate_text_findings(self) -> None:
        """Invokes finding integration module for novel text."""
        from src import integrate_findings

        logger.info(
            f"Calling: integrate_findings.integrate_findings_in_dir(output_dir='{self.output_dir}', model='{self.model}')"
        )
        try:
            success = integrate_findings.integrate_findings_in_dir(
                self.output_dir, self.model
            )
            if not success:
                raise IntegrationError("Failed to integrate findings in directory.")
        except IntegrationError:
            raise
        except Exception as e:
            raise IntegrationError(f"Unexpected integration error: {e}") from e

    def integrate_plot_findings(self, target_path: str) -> None:
        """Invokes plot finding integration module for novel plots."""
        from src import integrate_plot_findings

        logger.info("Integrating plot review results...")
        try:
            success = integrate_plot_findings.integrate_plot_findings_in_dir(
                self.output_dir, target_path, self.model
            )
            if not success:
                raise IntegrationError(
                    "Failed to integrate plot findings in directory."
                )
        except IntegrationError:
            raise
        except Exception as e:
            raise IntegrationError(f"Unexpected plot integration error: {e}") from e
